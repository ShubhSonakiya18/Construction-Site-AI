"""
app/api/dependencies.py — Shared FastAPI dependencies: DB session and current user.

Why get_db() yields the SYNC Session (not get_async_session()):
    See database/session.py module docstring and docs/BACKEND_ARCHITECTURE.md
    "Why the repository layer stays sync-only." database/repositories/*.py
    call session.execute()/.get()/.flush() without await — handing them an
    AsyncSession would silently return unawaited coroutines. FastAPI runs
    sync dependency generators (`def`, not `async def`) in a worker
    threadpool automatically, so routers built on get_db() do not block the
    event loop despite using the sync Session.

Why get_app_settings() reads request.app.state.settings, NOT get_settings():
    create_app(settings=...) accepts an explicit Settings override
    specifically so tests can build an isolated app with a known
    JWT secret (see tests/conftest_api.py test_settings fixture) — but
    Depends(get_settings) (the module-level lru_cache singleton from
    app/core/config.py) ignores that override entirely and always returns
    whatever Settings were first parsed from the real environment in this
    process. That is not a hypothetical: it was caught by
    tests/test_api_auth.py (login signed a token with the real JWT secret
    even though the test app was built with a distinct test secret) and
    tests/test_api_health.py (the /version endpoint reported the real
    environment instead of the test app's "testing" environment) failing.
    Every route that needs Settings must depend on get_app_settings(), which
    reads the actual Settings instance bound to the running app.

Why get_current_user() decodes the JWT itself (not a shared "auth service"):
    This is Sprint 7's entire auth surface — one token format, one secret,
    one algorithm. A dedicated AuthService class would be justified once
    Sprint 8 adds refresh tokens, password reset, or multiple auth schemes;
    for now it would be a one-method wrapper adding indirection without
    benefit.

Company scoping:
    CurrentUser.company_id (embedded in the JWT at login — see
    app/api/v1/auth.py) is what every list/detail route uses to scope
    queries to the authenticated tenant, per the multi-tenancy design in
    database/models/company.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generator
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import decode_access_token
from database.config import DatabaseConfig
from database.session import get_engine, get_session

_bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a sync database Session for the duration of one request.

    FastAPI treats a `def` (not `async def`) generator dependency as
    sync work and runs it in a threadpool — see module docstring.
    """
    engine = get_engine(DatabaseConfig.from_env())
    with get_session(engine) as session:
        yield session


def get_app_settings(request: Request) -> Settings:
    """Return the Settings instance bound to the running app (set in
    create_app()), NOT the process-wide get_settings() singleton — see
    module docstring for why this distinction matters for tests and for
    any future multi-app-instance deployment."""
    return request.app.state.settings


@dataclass(frozen=True)
class CurrentUser:
    """The authenticated principal for the current request, decoded from
    the JWT's claims — no extra DB round-trip needed to know who is making
    the request or which company they belong to."""

    user_id: UUID
    company_id: UUID
    role: str
    email: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    settings: Settings = Depends(get_app_settings),
) -> CurrentUser:
    """Decode and validate the Bearer JWT, returning the CurrentUser.

    Raises HTTP 401 if the header is missing, the token is malformed,
    expired, or has an invalid signature — decode_access_token() never
    raises itself (see app/core/security.py), so every failure mode is
    handled uniformly here.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Provide a Bearer token in the Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = decode_access_token(
        credentials.credentials,
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return CurrentUser(
            user_id=UUID(claims["sub"]),
            company_id=UUID(claims["company_id"]),
            role=claims["role"],
            email=claims["email"],
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing required claims.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_role(*allowed_roles: str):
    """Dependency factory: raises HTTP 403 unless the current user's role
    is one of allowed_roles. Usage:

        @router.post("/daily-logs/{id}/approve")
        def approve(..., user: CurrentUser = Depends(require_role("owner", "project_manager"))):
            ...
    """

    def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not permitted to perform this action.",
            )
        return user

    return _check
