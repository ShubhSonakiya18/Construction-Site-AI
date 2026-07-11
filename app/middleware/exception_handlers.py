"""
app/middleware/exception_handlers.py — Centralized exception -> APIResponse mapping.

Why these are FastAPI exception handlers (app.add_exception_handler), not
another BaseHTTPMiddleware:
    Exception handlers registered via add_exception_handler() run closer to
    the ASGI boundary than middleware — they catch exceptions raised by
    dependencies (e.g. app/api/dependencies.py's get_current_user raising
    HTTPException) and by Pydantic request validation, neither of which a
    BaseHTTPMiddleware's try/except around call_next() reliably sees in all
    FastAPI versions. This is the documented, idiomatic FastAPI pattern for
    "every error becomes the same response shape."

Exception -> HTTP status mapping:
    RequestValidationError  -> 422  Pydantic body/query/path validation failure
    HTTPException            -> whatever status_code the route/dependency raised
    ValueError                -> 409  business-rule violation (e.g. wrong review
                                       status transition — see DailyLogRepository)
    TypeError                 -> 500  programming error (wrong repository usage)
    Exception (catch-all)     -> 500  unexpected — logged with full traceback
                                       server-side, but the client only ever
                                       sees a generic message. Never leak
                                       internal exception text, stack traces,
                                       or file paths to the client.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.envelope import ErrorDetail, error_response

logger = logging.getLogger("app.errors")


def _json(status_code: int, envelope) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=envelope.model_dump(mode="json"))


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    envelope = error_response(
        message=str(exc.detail),
        errors=[ErrorDetail(code="http_error", message=str(exc.detail))],
    )
    return _json(exc.status_code, envelope)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [
        ErrorDetail(
            code="validation_error",
            message=err["msg"],
            field=".".join(str(loc) for loc in err["loc"] if loc != "body"),
        )
        for err in exc.errors()
    ]
    envelope = error_response(message="Request validation failed.", errors=errors)
    return _json(status.HTTP_422_UNPROCESSABLE_ENTITY, envelope)


async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Repository business-rule violations (e.g. DailyLogRepository.approve()
    called on an already-approved log) surface here as HTTP 409 Conflict."""
    envelope = error_response(
        message=str(exc),
        errors=[ErrorDetail(code="business_rule_violation", message=str(exc))],
    )
    return _json(status.HTTP_409_CONFLICT, envelope)


async def type_error_handler(request: Request, exc: TypeError) -> JSONResponse:
    logger.error("TypeError on %s %s: %s", request.method, request.url.path, exc)
    envelope = error_response(
        message="Internal server error.",
        errors=[ErrorDetail(code="internal_error", message="An internal error occurred.")],
    )
    return _json(status.HTTP_500_INTERNAL_SERVER_ERROR, envelope)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all — logs the full exception server-side (with traceback via
    logger.exception), but the client response never includes exception
    text, type name, or any internal detail."""
    logger.exception(
        "Unhandled exception on %s %s", request.method, request.url.path
    )
    envelope = error_response(
        message="An unexpected error occurred. Please try again or contact support.",
        errors=[ErrorDetail(code="internal_error", message="An unexpected error occurred.")],
    )
    return _json(status.HTTP_500_INTERNAL_SERVER_ERROR, envelope)


def register_exception_handlers(app: FastAPI) -> None:
    """Wire all handlers onto the FastAPI app. Called once from create_app()."""
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValueError, value_error_handler)
    app.add_exception_handler(TypeError, type_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
