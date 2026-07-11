"""
app/middleware/logging.py — Structured request/response logging.

Every request produces exactly one log line, emitted after the response is
ready, containing: request_id, method, path, status_code, duration_ms.

What is deliberately NEVER logged:
    - Request/response bodies (may contain passwords, JWTs in refresh flows,
      raw transcripts, or AI-generated content).
    - The Authorization header or any bearer token.
    - GROQ_API_KEY or any other secret — this middleware never touches
      request headers' values, only names, and only for the few explicitly
      allow-listed ones (none, currently).

Why a plain logging.Logger (not a JSON structlog setup):
    No other Sprint 1-6 module in this codebase uses structured JSON
    logging — every logger.info() call across speech/, extraction/,
    generation/, database/ uses the stdlib `logging` module with a
    printf-style format string. Introducing a second logging paradigm for
    just this one middleware would fragment log output between two formats
    in the same process. The structured fields (request_id, duration_ms,
    etc.) are still present — just as named fields in one formatted line,
    consistent with how e.g. transcribe.py already logs
    "OK  <id>  <duration>s ... took <time>s".
"""
from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.request")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Logs one line per request: request_id, method, path, status, duration_ms."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.monotonic()
        request_id = getattr(request.state, "request_id", "-")

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.monotonic() - start) * 1000
            logger.exception(
                "request_id=%s method=%s path=%s status=500 duration_ms=%.1f (unhandled exception)",
                request_id, request.method, request.url.path, duration_ms,
            )
            raise

        duration_ms = (time.monotonic() - start) * 1000
        log_level = logging.WARNING if response.status_code >= 400 else logging.INFO
        logger.log(
            log_level,
            "request_id=%s method=%s path=%s status=%d duration_ms=%.1f",
            request_id, request.method, request.url.path, response.status_code, duration_ms,
        )
        return response
