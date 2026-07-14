"""app/schemas/auth.py — Request/response models for the /api/v1/auth/* router.

Sprint 7 (unchanged): LoginRequest. LoginResponseData is extended in
Sprint 8 (additive fields only — refresh_token, session_id — no existing
field removed or retyped, so a Sprint 7 client parsing this response still
works unmodified).
Sprint 8 (new): refresh/logout/logout-all/password-change schemas. See
docs/AUTHENTICATION_ARCHITECTURE.md for the full flow each of these
belongs to.
"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)
    device_name: str | None = Field(
        default=None,
        max_length=200,
        description="Optional client-supplied label for this session, e.g. "
        "'Sarah's iPhone'. Shown in a future session-list endpoint.",
    )


class LoginResponseData(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user_id: str
    company_id: str
    role: str
    email: str
    # ── Sprint 8 additions (additive — Sprint 7 clients unaffected) ──────────
    refresh_token: str = Field(
        ..., description="Opaque token for POST /auth/refresh. Store securely "
        "(e.g. httpOnly cookie or secure storage) — it is a long-lived credential."
    )
    refresh_token_expires_in_days: int
    session_id: str = Field(
        ..., description="This login's UserSession id — identifies this "
        "specific device/session for a future 'log out this device' UI."
    )


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class RefreshResponseData(BaseModel):
    """Returned by POST /auth/refresh. Both tokens are NEW — the access
    token is freshly signed and the refresh token has been rotated (the
    one submitted in the request is now revoked). See
    docs/AUTHENTICATION_ARCHITECTURE.md 'Token Rotation'."""

    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    refresh_token: str
    refresh_token_expires_in_days: int
    session_id: str


class LogoutRequest(BaseModel):
    refresh_token: str = Field(
        ..., min_length=1,
        description="The session to revoke. Only this device is logged out.",
    )


class LogoutResponseData(BaseModel):
    session_id: str
    revoked: bool = True


class LogoutAllResponseData(BaseModel):
    sessions_revoked: int = Field(
        ..., description="Number of previously-active sessions revoked, "
        "across every device the caller was logged in on."
    )


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class ChangePasswordResponseData(BaseModel):
    sessions_revoked: int = Field(
        ..., description="Every other session was logged out as a security "
        "measure — see docs/AUTHENTICATION_ARCHITECTURE.md 'Password Change'."
    )


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponseData(BaseModel):
    message: str = Field(
        default="If that email is registered, a reset link has been sent.",
        description="Deliberately identical regardless of whether the email "
        "exists — see docs/AUTHENTICATION_ARCHITECTURE.md 'Forgot Password'.",
    )


class ResetPasswordRequest(BaseModel):
    reset_token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class ResetPasswordResponseData(BaseModel):
    sessions_revoked: int


class CurrentUserResponseData(BaseModel):
    """Returned by GET /auth/me."""

    user_id: str
    company_id: str
    email: str
    first_name: str
    last_name: str
    role: str
    is_active: bool
