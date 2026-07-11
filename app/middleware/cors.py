"""
app/middleware/cors.py — CORS configuration, derived from Settings.

Why a separate function instead of calling CORSMiddleware inline in
create_app.py:
    Keeps the "what origins/methods/headers are allowed" policy in one
    reviewable place, and keeps create_app.py's middleware-registration
    block readable as a flat list of `app.add_middleware(...)` calls.

Production guard:
    Settings.cors_allow_origins defaults to ["*"] (any origin) — convenient
    for local development, actively dangerous in production if combined
    with allow_credentials=True (browsers/CORS spec forbid credentialed
    "*" responses, and permissive CORS is a common real-world
    misconfiguration). create_app.py's startup check
    (Settings.is_production and origins == ["*"]) fails fast rather than
    silently deploying an open CORS policy.
"""
from __future__ import annotations

from app.core.config import Settings


def cors_kwargs(settings: Settings) -> dict:
    """Return the kwargs for Starlette's CORSMiddleware, derived from Settings."""
    origins = settings.cors_allow_origins
    return {
        "allow_origins": origins,
        # Credentialed requests (cookies, Authorization header) cannot be
        # combined with allow_origins=["*"] per the CORS spec — browsers
        # reject it. This project uses Bearer tokens (not cookies), sent
        # via the Authorization header, which does NOT require
        # allow_credentials=True to work cross-origin.
        "allow_credentials": origins != ["*"],
        "allow_methods": ["*"],
        "allow_headers": ["*"],
        "expose_headers": ["X-Request-ID"],
    }
