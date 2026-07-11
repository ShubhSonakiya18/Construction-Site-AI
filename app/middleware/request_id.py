"""
app/middleware/request_id.py — Request ID assignment and propagation.

Why a ContextVar (not request.state):
    request.state.request_id works fine inside a route handler, which
    always has access to the `request` object. But app/schemas/envelope.py's
    success_response()/error_response() helpers are called from many places
    that do NOT have a `request` object in scope — deep inside a service
    function, or from an exception handler that only receives the exception.
    A ContextVar is readable from anywhere in the same async task without
    threading `request` through every function signature.

Why every response gets an X-Request-ID header:
    Lets a client (or this team, reading logs) correlate a specific HTTP
    response with the corresponding server-side log lines — every log
    statement in LoggingMiddleware includes the same ID.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Return the current request's ID, or a freshly generated one if called
    outside any request context (e.g. a unit test that doesn't go through
    the middleware stack)."""
    current = _request_id_ctx.get()
    return current or str(uuid.uuid4())


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns a UUID to every incoming request (or reuses an inbound
    X-Request-ID header, so a load balancer or upstream service can supply
    its own trace ID), stores it in a ContextVar for the duration of the
    request, and echoes it back as a response header.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get("X-Request-ID")
        request_id = incoming if incoming else str(uuid.uuid4())
        token = _request_id_ctx.set(request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        finally:
            _request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response
