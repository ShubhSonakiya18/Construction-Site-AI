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

Why get_current_user() looks the user up in the database (not just
trusting the JWT claims):
    A syntactically valid, correctly-signed JWT can outlive the user it
    names — the token has up to jwt_access_token_expire_minutes (default
    60) of validity regardless of what happens to the account in that
    window. User has SoftDeleteMixin (a user can be deactivated at any
    time) and an independent is_active flag. Building CurrentUser from
    claims alone (the original Sprint 7 implementation) meant a
    soft-deleted or deactivated user's still-valid token would sail
    through authentication, and any endpoint writing user.user_id into a
    real FK column (e.g. AudioFile.uploaded_by_id -> users.id) would crash
    with an unhandled psycopg2.errors.ForeignKeyViolation surfaced to the
    client as a raw 500 traceback — confirmed live against
    POST /audio/upload with a token naming a UUID that had never been a
    User row at all (the general case a deleted/deactivated user's token
    also falls into: "sub claim does not resolve to a live user"). One
    indexed primary-key lookup per authenticated request is the fix —
    UserRepository.get_by_id() already excludes soft-deleted rows by
    default (BaseRepository convention, Sprint 6), so this reuses existing
    repository behavior rather than adding a second definition of "does
    this user still exist."

Why the 401 message never distinguishes "deleted" from "deactivated" from
"never existed":
    Same rationale as login's identical wrong-password/no-such-user
    response (see app/api/v1/auth.py) — telling an attacker which case
    occurred is free reconnaissance. The response is uniformly "Invalid or
    expired token." for all three; only server-side logs (not visible to
    the client) can distinguish them if that's ever needed for debugging.

Company scoping:
    CurrentUser.company_id is read from the database at lookup time (the
    live User row), not from the JWT claim — if the user's company_id ever
    changes after a token was issued, requests must scope to the current
    company, not a stale one embedded in an old token.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generator
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.permissions import Permission, role_has_permission
from app.core.security import decode_access_token
from app.middleware.request_id import get_request_id
from app.services.audit_helpers import safe_log_event
from database.config import DatabaseConfig
from database.repositories.company import UserRepository
from database.repositories.generation import AuditLogRepository
from database.session import get_engine, get_session


def _client_ip(request: Request) -> str | None:
    """Best-effort client IP — same logic as app/api/v1/auth.py's helper,
    duplicated here (not imported) to avoid a dependencies.py -> auth.py
    import that would invert this module's usual role as something
    OTHER routers depend on, not the reverse."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None

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


_INVALID_TOKEN_DETAIL = "Invalid or expired token."


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    settings: Settings = Depends(get_app_settings),
    session: Session = Depends(get_db),
) -> CurrentUser:
    """Decode the Bearer JWT AND verify the user it names still exists and
    is active, returning the CurrentUser built from the live database row.

    Raises HTTP 401 uniformly for every invalid-auth case: missing header,
    malformed/expired/bad-signature token, missing claims, or a token whose
    subject no longer resolves to an active user (deleted, deactivated, or
    never existed) — see module docstring for why the database check exists
    and why the response never distinguishes between these cases.

    Sprint 8, Subsystem 6: every rejection path here logs a
    "security.unauthorized_access" audit event (fail-open — see
    app/services/audit_helpers.py — this dependency runs on nearly every
    request, so a logging hiccup must never turn into a site-wide outage).
    Successful authentication is NOT separately audited here — that
    would be one row per authenticated request, which is log volume, not
    a security signal; a caller's own action (login, an approved daily
    log, etc.) is what gets its own success event, not the fact that
    their token happened to work on some unrelated request.
    """
    audit = AuditLogRepository(session)
    request_id = get_request_id()
    ip_address = _client_ip(request)
    user_agent = request.headers.get("User-Agent")

    def _log_unauthorized(reason: str) -> None:
        safe_log_event(
            audit, "security.unauthorized_access",
            ip_address=ip_address, user_agent=user_agent,
            request_id=request_id, success=False,
            metadata={"reason": reason, "path": str(request.url.path)},
        )

    if credentials is None:
        _log_unauthorized("missing_credentials")
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
        _log_unauthorized("invalid_jwt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_TOKEN_DETAIL,
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        _log_unauthorized("missing_claims")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing required claims.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # Verify the user still exists (get_by_id excludes soft-deleted rows by
    # default) and is active — a syntactically valid, correctly-signed token
    # can outlive the account it names. See module docstring.
    user = UserRepository(session).get_by_id(user_id)
    if user is None or not user.is_active:
        safe_log_event(
            audit, "security.unauthorized_access",
            entity_type="user", entity_id=user_id, actor_id=user_id,
            ip_address=ip_address, user_agent=user_agent,
            request_id=request_id, success=False,
            metadata={"reason": "user_not_found_or_inactive", "path": str(request.url.path)},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_TOKEN_DETAIL,
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CurrentUser(
        user_id=user.id,
        company_id=user.company_id,
        role=user.role,
        email=user.email,
    )


def require_role(*allowed_roles: str):
    """Dependency factory: raises HTTP 403 unless the current user's role
    is one of allowed_roles.

    Sprint 8 note: prefer require_permission() (below) for anything that
    represents a business capability — "can approve a daily log," "can
    create a user" — rather than naming roles directly in a router. This
    function remains for the rare case that's genuinely about the role
    itself (e.g. a UI-only distinction with no permission behind it), and
    because app/core/permissions.py's ROLE_PERMISSIONS mapping is itself
    keyed by these same role strings — require_role() and
    require_permission() are two views onto the same role model, not
    competing mechanisms.

    Usage:
        @router.post("/some-role-specific-endpoint")
        def handler(..., user: CurrentUser = Depends(require_role("owner"))):
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


def require_permission(permission: Permission):
    """Dependency factory: raises HTTP 403 unless the current user's role
    grants `permission` (per app/core/permissions.py:ROLE_PERMISSIONS).

    This is the Sprint 8 replacement for hardcoding role lists at the
    router: routers ask "can this user approve a daily log?"
    (require_permission(Permission.DAILY_LOG_APPROVE)), not "is this user
    an owner or a project_manager?" (require_role("owner",
    "project_manager")) — the latter means every router that cares about
    approval rights has to independently know and agree on which roles
    that includes, and stays in sync only by discipline. With
    require_permission(), which roles currently grant DAILY_LOG_APPROVE is
    decided in exactly one place (ROLE_PERMISSIONS) and every router
    asking about that permission automatically reflects it.

    Usage:
        @router.post("/daily-logs/{id}/approve")
        def approve(
            ...,
            user: CurrentUser = Depends(require_permission(Permission.DAILY_LOG_APPROVE)),
        ):
            ...
    """

    def _check(
        request: Request,
        user: CurrentUser = Depends(get_current_user),
        session: Session = Depends(get_db),
    ) -> CurrentUser:
        if not role_has_permission(user.role, permission):
            safe_log_event(
                AuditLogRepository(session), "security.forbidden_access",
                entity_type="user", entity_id=user.user_id,
                actor_id=user.user_id, company_id=user.company_id,
                ip_address=_client_ip(request), user_agent=request.headers.get("User-Agent"),
                request_id=get_request_id(), success=False,
                metadata={
                    "required_permission": permission.value, "role": user.role,
                    "path": str(request.url.path),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' does not have permission '{permission.value}'.",
            )
        return user

    return _check
