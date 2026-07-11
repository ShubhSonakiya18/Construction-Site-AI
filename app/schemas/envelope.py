"""
app/schemas/envelope.py — The standard API response envelope.

Every endpoint in this API — success or error — returns the same top-level
shape:

    {
        "success": true,
        "message": "Daily log retrieved successfully.",
        "data": { ... the actual payload ... },
        "metadata": { ... optional: pagination, counts, etc. ... },
        "timestamp": "2026-07-11T14:32:00Z",
        "request_id": "a1b2c3d4-..."
    }

Why a generic APIResponse[T] instead of returning raw resource models:
    A bare `DailyLogRead` response forces every client to special-case
    errors (different shape entirely: FastAPI's default HTTPException body
    is {"detail": "..."}) versus success responses. A single envelope shape
    means client code has exactly one parsing path, and success/error is a
    boolean flag, not a shape difference. The `[T]` generic means OpenAPI
    still documents the real `data` type per endpoint (e.g.
    APIResponse[DailyLogRead]) instead of a vague `data: object`.

Why request_id and timestamp are set by success_response()/error_response()
helpers, not by each route handler:
    If every route had to remember `request_id=get_request_id()`, someone
    would eventually forget it. The helpers pull request_id from the
    contextvar set by RequestIDMiddleware (app/middleware/request_id.py) —
    a route never needs to know the current request's ID to build a
    response.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

from app.middleware.request_id import get_request_id

T = TypeVar("T")


class PaginationMeta(BaseModel):
    """Standard pagination metadata, used in the `metadata` field of list responses."""

    total: int = Field(..., description="Total number of matching records.")
    limit: int = Field(..., description="Page size requested.")
    offset: int = Field(..., description="Number of records skipped.")
    count: int = Field(..., description="Number of records in this response.")


class ErrorDetail(BaseModel):
    """One structured error item. A response may carry multiple (e.g. per-field
    validation errors)."""

    code: str = Field(..., description="Machine-readable error code, e.g. 'not_found'.")
    message: str = Field(..., description="Human-readable explanation.")
    field: Optional[str] = Field(
        default=None, description="Request field this error relates to, if applicable."
    )


class APIResponse(BaseModel, Generic[T]):
    """The standard envelope wrapping every API response body."""

    success: bool
    message: str
    data: Optional[T] = None
    metadata: Optional[dict] = None
    errors: Optional[list[ErrorDetail]] = None
    timestamp: datetime
    request_id: str


def success_response(
    data: T,
    *,
    message: str = "Request completed successfully.",
    metadata: Optional[dict] = None,
) -> APIResponse[T]:
    """Build a success envelope. Use as the return value of a route handler."""
    return APIResponse[T](
        success=True,
        message=message,
        data=data,
        metadata=metadata,
        errors=None,
        timestamp=datetime.now(timezone.utc),
        request_id=get_request_id(),
    )


def error_response(
    *,
    message: str,
    errors: Optional[list[ErrorDetail]] = None,
) -> APIResponse[None]:
    """Build an error envelope. Used by exception handlers
    (app/middleware/exception_handlers.py), not typically called directly
    from route handlers — raise an HTTPException instead and let the
    handler build this."""
    return APIResponse[None](
        success=False,
        message=message,
        data=None,
        metadata=None,
        errors=errors,
        timestamp=datetime.now(timezone.utc),
        request_id=get_request_id(),
    )
