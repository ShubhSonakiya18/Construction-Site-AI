"""
app/create_app.py — Application factory.

Why a factory function (not a module-level `app = FastAPI()`):
    A module-level app object is constructed at import time with whatever
    Settings happen to be in os.environ at that moment — there is no clean
    way to build a second app instance with different settings for tests
    (test config, isolated CORS, etc.) without monkeypatching os.environ
    before every import. create_app(settings=...) accepts an explicit
    Settings override, so tests/test_api_*.py builds a fully isolated app
    per test session without touching the real .env.

Startup/shutdown (lifespan):
    FastAPI's lifespan context manager is the Sprint 7-era replacement for
    the deprecated @app.on_event("startup"/"shutdown") decorators. Used
    here for exactly one thing: a production safety check (refuse to start
    with the default JWT secret or a wide-open CORS policy in production).
    Database connections are NOT eagerly created at startup — get_engine()
    is lazy (see database/session.py) and creates the pool on first use,
    consistent with how every Sprint 1-6 CLI tool already behaves.

Middleware registration order (outermost first — see app/middleware/__init__.py):
    1. RequestIDMiddleware — must run first so every other layer can read
       the request ID.
    2. LoggingMiddleware — logs using the request ID from step 1.
    3. CORSMiddleware — Starlette built-in.
    (GZipMiddleware and TrustedHostMiddleware are also Starlette built-ins,
    added here for production-readiness per Sprint 7 requirements.)

Extension point for Celery (Sprint 8, NOT implemented here):
    Sprint 7 uses FastAPI's BackgroundTasks (see app/services/pipeline_service.py)
    for the transcribe -> extract -> persist -> generate chain. The service
    layer function signature (`def run_pipeline(audio_file_id: UUID) -> None`,
    no return value, no request context) is deliberately shaped so that
    swapping BackgroundTasks for a Celery task decorator later is a
    one-line change at the call site (audio.py) — the function body itself
    does not change. See docs/BACKEND_ARCHITECTURE.md "Background Task
    Readiness" for the full extension-point list.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1 import auth as auth_router
from app.api.v1 import audio as audio_router
from app.api.v1 import daily_logs as daily_logs_router
from app.api.v1 import health as health_router
from app.api.v1 import projects as projects_router
from app.core.config import Settings, get_settings
from app.middleware.cors import cors_kwargs
from app.middleware.exception_handlers import register_exception_handlers
from app.middleware.logging import LoggingMiddleware
from app.middleware.request_id import RequestIDMiddleware

logger = logging.getLogger("app.startup")

_INSECURE_DEFAULT_JWT_SECRET = "dev-insecure-secret-change-me"


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings: Settings = app.state.settings

    if settings.is_production:
        if settings.jwt_secret_key == _INSECURE_DEFAULT_JWT_SECRET:
            raise RuntimeError(
                "Refusing to start: JWT_SECRET_KEY is still the insecure "
                "development default. Set a real secret in the production "
                "environment before starting."
            )
        if settings.cors_allow_origins == ["*"]:
            raise RuntimeError(
                "Refusing to start: CORS_ALLOW_ORIGINS is '*' (any origin) "
                "in production. Set an explicit comma-separated origin list."
            )

    logger.info(
        "Starting %s v%s (environment=%s)",
        settings.app_title, settings.app_version, settings.environment,
    )
    yield
    logger.info("Shutting down %s", settings.app_title)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and fully configure a FastAPI application instance.

    Args:
        settings: Explicit Settings to use instead of the process-wide
            cached get_settings(). Tests pass a Settings(...) constructed
            with test-specific values (e.g. a known JWT secret) so token
            creation/verification in tests is deterministic and isolated
            from whatever .env happens to be on disk.
    """
    resolved_settings = settings or get_settings()

    app = FastAPI(
        title=resolved_settings.app_title,
        description=resolved_settings.app_description,
        version=resolved_settings.app_version,
        contact={
            "name": resolved_settings.app_contact_name,
            "email": resolved_settings.app_contact_email,
        },
        license_info={"name": "Proprietary"},
        openapi_tags=[
            {"name": "Health", "description": "Liveness, readiness, and diagnostic endpoints."},
            {"name": "Auth", "description": "JWT login."},
            {"name": "Audio", "description": "Voice recording upload and pipeline status."},
            {"name": "Daily Logs", "description": "Daily log retrieval, review lifecycle, and AI generation."},
            {"name": "Projects", "description": "Project and per-project daily log listing."},
        ],
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        debug=resolved_settings.debug,
        lifespan=_lifespan,
    )
    app.state.settings = resolved_settings

    # ── Middleware (registration order matters — see module docstring) ───────
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(CORSMiddleware, **cors_kwargs(resolved_settings))
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    if resolved_settings.is_production:
        # In development/testing, TrustedHostMiddleware would block
        # TestClient's default "testserver" host — restrict it to
        # production only, where the real deployed hostname is known.
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

    register_exception_handlers(app)

    # ── Routers, all under /api/v1 ────────────────────────────────────────────
    api_v1_prefix = "/api/v1"
    app.include_router(health_router.router, prefix=api_v1_prefix)
    app.include_router(auth_router.router, prefix=api_v1_prefix)
    app.include_router(audio_router.router, prefix=api_v1_prefix)
    app.include_router(daily_logs_router.router, prefix=api_v1_prefix)
    app.include_router(projects_router.router, prefix=api_v1_prefix)

    return app
