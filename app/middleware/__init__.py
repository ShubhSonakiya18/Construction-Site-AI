"""app/middleware/ — Cross-cutting request/response processing.

Registered in app/create_app.py in this order (outermost first):
    1. RequestIDMiddleware   — assigns/propagates X-Request-ID
    2. LoggingMiddleware     — structured request/response logging + timing
    3. CORSMiddleware        — Starlette's built-in, configured from Settings
    (TrustedHostMiddleware and GZipMiddleware are Starlette built-ins,
    also wired in create_app.py.)

Order matters: middleware wraps in registration order, so RequestIDMiddleware
must run first so every other middleware and every route handler can read
the request ID via get_request_id().
"""
