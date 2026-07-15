"""
app/middleware/security_headers.py — Standard defensive HTTP response headers.

Sprint 8, Subsystem 5 (Security Hardening). Mirrors app/middleware/cors.py's
pattern: a small, reviewable middleware class that adds one clearly-scoped
concern to every response, registered alongside the other middleware in
create_app.py.

Headers set, and why each one:
    X-Content-Type-Options: nosniff
        Stops a browser from MIME-sniffing a response into a different
        content type than declared (e.g. treating an uploaded audio file's
        response as executable script) — this API serves JSON almost
        exclusively, but audio.py's upload path proves a request body can
        carry attacker-influenced content, so this is a real, not just
        theoretical, precaution.
    X-Frame-Options: DENY
        Prevents this API's responses from being framed by another site
        (clickjacking defense) — irrelevant to a pure JSON API in most
        browsers' interpretation, but costs nothing and is a standard
        baseline header security scanners check for.
    Referrer-Policy: strict-origin-when-cross-origin
        Limits how much of this API's URLs (which can contain UUIDs — not
        secrets, but not meant for third-party analytics either) leak via
        the Referer header when a client navigates away.
    Strict-Transport-Security (production only)
        Tells browsers to only ever connect over HTTPS for a period after
        the first successful HTTPS response — only sent when
        Settings.is_production, matching create_app.py's existing pattern
        of production-only hardening (see the lifespan check for the JWT
        secret and CORS policy). Sending HSTS in development would be
        actively harmful (it would make a browser refuse to connect to a
        local http:// dev server after visiting once).

Why NOT a Content-Security-Policy header:
    CSP is meaningful for a server that renders HTML responses handling
    an attacker-influenced DOM. This is a pure JSON API — /docs and
    /redoc (FastAPI's own Swagger/ReDoc UI) are the only HTML this
    process ever serves, and a CSP tuned for those pages would need
    separate handling since they're not the API's own routes. Deferred
    until this backend serves genuine application HTML (Sprint 9+
    frontend, if ever proxied through this same origin) rather than
    added speculatively now.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, is_production: bool) -> None:
        super().__init__(app)
        self._is_production = is_production

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if self._is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response
