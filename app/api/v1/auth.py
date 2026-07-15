"""
app/api/v1/auth.py — Authentication endpoints.

Sprint 7 (unchanged behavior, extended response): POST /auth/login.
Sprint 8 (new): POST /auth/refresh, /logout, /logout-all,
/change-password, /forgot-password, /reset-password, GET /auth/me.

Every route here is a thin translator between HTTP and AuthService
(app/services/auth_service.py) — the actual multi-step logic (rotation,
mass-revocation, reuse detection) lives in the service, per this file's
original Sprint 7 docstring: a service class becomes justified "once
Sprint 8 adds refresh tokens, password reset, or multiple auth schemes."
That threshold is now crossed for every route except the original login
one-liner, but login is kept on the same service for a single, consistent
entry point.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_app_settings, get_current_user, get_db
from app.core.config import Settings
from app.core.rate_limit import RateLimiter, get_rate_limiter
from app.middleware.request_id import get_request_id
from app.schemas.auth import (
    ChangePasswordRequest,
    ChangePasswordResponseData,
    CurrentUserResponseData,
    ForgotPasswordRequest,
    ForgotPasswordResponseData,
    LoginRequest,
    LoginResponseData,
    LogoutAllResponseData,
    LogoutRequest,
    LogoutResponseData,
    RefreshRequest,
    RefreshResponseData,
    ResetPasswordRequest,
    ResetPasswordResponseData,
)
from app.schemas.envelope import APIResponse, success_response
from app.services.auth_service import AuthService
from database.repositories.company import UserRepository

router = APIRouter(prefix="/auth", tags=["Auth"])


def _client_ip(request: Request) -> str | None:
    """Best-effort client IP: honors X-Forwarded-For (set by a reverse
    proxy/load balancer) if present, falls back to the direct connection.
    Never raises — returns None if neither is available (e.g. in-process
    TestClient requests with no real socket)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post(
    "/login",
    response_model=APIResponse[LoginResponseData],
    summary="Log in and receive an access token + refresh token",
    description=(
        "Verifies email + password and returns a short-lived Bearer access "
        "token plus a long-lived refresh token. Sprint 7 provided access-"
        "token-only login; Sprint 8 adds the refresh token and creates a "
        "UserSession row for this device — see "
        "docs/AUTHENTICATION_ARCHITECTURE.md."
    ),
)
def login(
    body: LoginRequest,
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> APIResponse[LoginResponseData]:
    service = AuthService(session, settings, rate_limiter=rate_limiter)
    user, pair = service.login(
        email=body.email,
        password=body.password,
        device_name=body.device_name,
        user_agent=request.headers.get("User-Agent"),
        ip_address=_client_ip(request),
        request_id=get_request_id(),
    )
    return success_response(
        LoginResponseData(
            access_token=pair.access_token,
            expires_in_minutes=pair.access_token_expires_in_minutes,
            user_id=str(user.id),
            company_id=str(user.company_id),
            role=user.role,
            email=user.email,
            refresh_token=pair.refresh_token,
            refresh_token_expires_in_days=pair.refresh_token_expires_in_days,
            session_id=str(pair.session_id),
        ),
        message="Login successful.",
    )


@router.post(
    "/refresh",
    response_model=APIResponse[RefreshResponseData],
    summary="Exchange a refresh token for a new access + refresh token pair",
    description=(
        "Rotates the refresh token: the submitted token is revoked and a "
        "new one is issued along with a fresh access token. The submitted "
        "token cannot be used again — see "
        "docs/AUTHENTICATION_ARCHITECTURE.md 'Token Rotation'."
    ),
)
def refresh(
    body: RefreshRequest,
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> APIResponse[RefreshResponseData]:
    service = AuthService(session, settings)
    _user, pair = service.refresh(
        raw_refresh_token=body.refresh_token,
        user_agent=request.headers.get("User-Agent"),
        ip_address=_client_ip(request),
        request_id=get_request_id(),
    )
    return success_response(
        RefreshResponseData(
            access_token=pair.access_token,
            expires_in_minutes=pair.access_token_expires_in_minutes,
            refresh_token=pair.refresh_token,
            refresh_token_expires_in_days=pair.refresh_token_expires_in_days,
            session_id=str(pair.session_id),
        ),
        message="Token refreshed.",
    )


@router.post(
    "/logout",
    response_model=APIResponse[LogoutResponseData],
    summary="Log out the current device (revoke one refresh token)",
    description="Revokes the session backing the submitted refresh token. "
    "The access token already issued for that session remains valid until "
    "it naturally expires (it cannot be revoked — see "
    "docs/AUTHENTICATION_ARCHITECTURE.md 'Access Tokens vs Refresh Tokens').",
)
def logout(
    body: LogoutRequest,
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> APIResponse[LogoutResponseData]:
    service = AuthService(session, settings)
    session_id = service.logout(
        raw_refresh_token=body.refresh_token,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        request_id=get_request_id(),
    )
    return success_response(
        LogoutResponseData(session_id=str(session_id)),
        message="Logged out.",
    )


@router.post(
    "/logout-all",
    response_model=APIResponse[LogoutAllResponseData],
    summary="Log out every device (revoke all sessions for the current user)",
    description="Requires a valid access token. Revokes every active "
    "refresh token/session belonging to the authenticated user, across "
    "every device.",
)
def logout_all(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> APIResponse[LogoutAllResponseData]:
    service = AuthService(session, settings)
    revoked = service.logout_all(
        user_id=user.user_id,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        request_id=get_request_id(),
    )
    return success_response(
        LogoutAllResponseData(sessions_revoked=revoked),
        message=f"Logged out of {revoked} session(s).",
    )


@router.post(
    "/change-password",
    response_model=APIResponse[ChangePasswordResponseData],
    summary="Change the current user's password",
    description="Requires the current password. On success, every active "
    "session for this user is revoked (including the one making this "
    "request) — the client must log in again.",
)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> APIResponse[ChangePasswordResponseData]:
    service = AuthService(session, settings)
    user_row = UserRepository(session).get_by_id(user.user_id)
    revoked = service.change_password(
        user=user_row,
        current_password=body.current_password,
        new_password=body.new_password,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        request_id=get_request_id(),
    )
    return success_response(
        ChangePasswordResponseData(sessions_revoked=revoked),
        message="Password changed. Please log in again.",
    )


@router.post(
    "/forgot-password",
    response_model=APIResponse[ForgotPasswordResponseData],
    summary="Request a password reset token",
    description=(
        "Always returns the same generic message, whether or not the "
        "email is registered (prevents account enumeration). In "
        "development/testing only (no email provider exists yet — see "
        "docs/AUTHENTICATION_ARCHITECTURE.md 'Forgot Password'), the raw "
        "reset token is included in the response `metadata` for manual "
        "verification. Never returned in production."
    ),
)
def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> APIResponse[ForgotPasswordResponseData]:
    service = AuthService(session, settings, rate_limiter=rate_limiter)
    raw_token = service.forgot_password(
        email=body.email,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        request_id=get_request_id(),
    )
    metadata = None
    if raw_token is not None:
        # Non-production only — AuthService.forgot_password() itself
        # enforces this (always returns None when settings.is_production).
        metadata = {"dev_reset_token": raw_token}
    return success_response(
        ForgotPasswordResponseData(),
        message="If that email is registered, a reset link has been sent.",
        metadata=metadata,
    )


@router.post(
    "/reset-password",
    response_model=APIResponse[ResetPasswordResponseData],
    summary="Reset a password using a token from /forgot-password",
    description="Consumes the reset token (single-use), sets the new "
    "password, and revokes every active session for that user.",
)
def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> APIResponse[ResetPasswordResponseData]:
    service = AuthService(session, settings)
    _user, revoked = service.reset_password(
        raw_reset_token=body.reset_token,
        new_password=body.new_password,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        request_id=get_request_id(),
    )
    return success_response(
        ResetPasswordResponseData(sessions_revoked=revoked),
        message="Password reset. Please log in again.",
    )


@router.get(
    "/me",
    response_model=APIResponse[CurrentUserResponseData],
    summary="Get the currently authenticated user",
)
def get_me(
    user: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> APIResponse[CurrentUserResponseData]:
    user_row = UserRepository(session).get_by_id(user.user_id)
    return success_response(
        CurrentUserResponseData(
            user_id=str(user_row.id),
            company_id=str(user_row.company_id),
            email=user_row.email,
            first_name=user_row.first_name,
            last_name=user_row.last_name,
            role=user_row.role,
            is_active=user_row.is_active,
        ),
        message="Current user retrieved.",
    )
