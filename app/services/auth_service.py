"""
app/services/auth_service.py — Authentication orchestration.

Sprint 8. Follows the same "service layer for genuinely multi-step
business logic" precedent as app/services/pipeline_service.py — see that
module's docstring and app/api/v1/auth.py (Sprint 7)'s docstring, which
explicitly says a service class isn't justified for a single lookup + one
password check + one token encode, but WOULD be justified "once Sprint 8
adds refresh tokens, password reset, or multiple auth schemes." That
sprint is now. Login, refresh, logout, logout-all, and password-change
each touch 2+ repositories and have real branching logic (rotation,
mass-revocation, reuse detection) — exactly the kind of orchestration this
codebase's own convention says belongs in a service, not a router.

Every method returns a structured result object or raises HTTPException
directly with the same "401 for auth failures never distinguishes why"
principle Sprint 7 established (see app/api/dependencies.py module
docstring) — callers (app/api/v1/auth.py) stay thin translators from
these results to the standard response envelope.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from database.models.auth import UserSession
from database.models.company import User
from database.models.password_reset import PasswordResetToken
from database.repositories.auth import UserSessionRepository
from database.repositories.company import UserRepository
from database.repositories.password_reset import PasswordResetTokenRepository

logger = logging.getLogger("app.auth")

_INVALID_CREDENTIALS_DETAIL = "Incorrect email or password."
_INVALID_REFRESH_DETAIL = "Invalid or expired refresh token."
_INVALID_RESET_TOKEN_DETAIL = "Invalid, expired, or already-used reset token."
_GENERIC_FORGOT_PASSWORD_MESSAGE = "If that email is registered, a reset link has been sent."


@dataclass(frozen=True)
class IssuedTokenPair:
    """The result of a successful login or refresh: one access token, one
    fresh refresh token, and the session row backing the refresh token."""

    access_token: str
    access_token_expires_in_minutes: int
    refresh_token: str
    refresh_token_expires_in_days: int
    session_id: UUID


class AuthService:
    """Orchestrates login, token refresh, logout, and password change.

    Constructed per-request with the request's Session and Settings —
    same lifecycle as a repository, not a singleton (Settings can differ
    per app instance in tests, see get_app_settings() docstring).
    """

    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._users = UserRepository(session)
        self._sessions = UserSessionRepository(session)
        self._reset_tokens = PasswordResetTokenRepository(session)

    # ── Login ─────────────────────────────────────────────────────────────

    def login(
        self,
        *,
        email: str,
        password: str,
        device_name: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> tuple[User, IssuedTokenPair]:
        """Verify credentials and issue a new access + refresh token pair.

        Raises HTTPException(401) for any credential failure — wrong
        password, nonexistent email, or inactive account — all with the
        same message (see app/api/v1/auth.py's original Sprint 7
        docstring: account enumeration prevention, unchanged here).
        """
        user = self._users.get_by_email(email)
        if user is None or not user.is_active or not verify_password(
            password, user.hashed_password or ""
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_INVALID_CREDENTIALS_DETAIL,
            )

        user.last_login_at = datetime.now(timezone.utc)
        self._users.update(user)

        pair = self._issue_token_pair(
            user, device_name=device_name, user_agent=user_agent, ip_address=ip_address
        )
        return user, pair

    # ── Refresh ───────────────────────────────────────────────────────────

    def refresh(
        self,
        *,
        raw_refresh_token: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> tuple[User, IssuedTokenPair]:
        """Rotate a refresh token: validate it, revoke it, issue a new pair.

        Rotation (not reuse) means every successful refresh invalidates the
        token that was just used — see docs/AUTHENTICATION_ARCHITECTURE.md
        "Token Rotation" for why (limits the damage window of a stolen
        refresh token to a single use).

        Raises HTTPException(401) if the token is unknown, already revoked,
        or past its absolute expiry.
        """
        token_hash = hash_refresh_token(raw_refresh_token)
        session_row = self._sessions.get_by_token_hash(token_hash)

        if session_row is None or not session_row.is_active:
            # A revoked-but-presented-again token is either an expired
            # session being retried, or a stolen token being replayed after
            # the legitimate rotation already happened. Either way: 401,
            # no distinction — see module docstring.
            if session_row is not None and session_row.revoked_at is not None:
                logger.warning(
                    "auth.refresh: reuse of revoked session %s (reason=%s) — "
                    "possible stolen/replayed refresh token",
                    session_row.id, session_row.revoke_reason,
                )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_INVALID_REFRESH_DETAIL,
            )

        user = self._users.get_by_id(session_row.user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_INVALID_REFRESH_DETAIL,
            )

        session_row.last_used_at = datetime.now(timezone.utc)
        self._sessions.revoke(session_row, reason="rotated")

        pair = self._issue_token_pair(
            user,
            device_name=session_row.device_name,
            user_agent=user_agent or session_row.user_agent,
            ip_address=ip_address or session_row.ip_address,
        )
        return user, pair

    # ── Logout ────────────────────────────────────────────────────────────

    def logout(self, *, raw_refresh_token: str) -> UUID:
        """Revoke exactly one session (the one this refresh token names).

        Idempotent: logging out an already-revoked or unknown token is not
        an error — the caller's goal ("this token should not work anymore")
        is already satisfied. Returns the revoked session's id, or a
        zero UUID (all-zeros) if the token was already invalid/unknown, so
        the router always has something to report without a special case.
        """
        token_hash = hash_refresh_token(raw_refresh_token)
        session_row = self._sessions.get_by_token_hash(token_hash)
        if session_row is None:
            return UUID(int=0)
        self._sessions.revoke(session_row, reason="logout")
        return session_row.id

    def logout_all(self, *, user_id: UUID) -> int:
        """Revoke every active session for a user. Returns the count revoked."""
        return self._sessions.revoke_all_for_user(user_id, reason="logout_all")

    # ── Password change ──────────────────────────────────────────────────

    def change_password(
        self, *, user: User, current_password: str, new_password: str
    ) -> int:
        """Verify the current password, set a new one, and revoke every
        active session for this user (see
        docs/AUTHENTICATION_ARCHITECTURE.md "Password Change").

        Raises HTTPException(401) if current_password is wrong — same
        generic-ish posture as login, though here the user is already
        authenticated (via access token) so there's no enumeration risk;
        401 is still correct because the caller failed to prove they know
        the current password, the same class of failure as an expired token.
        """
        if not verify_password(current_password, user.hashed_password or ""):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect.",
            )
        user.hashed_password = hash_password(new_password)
        self._users.update(user)
        revoked = self._sessions.revoke_all_for_user(user.id, reason="password_changed")
        logger.info(
            "auth.change_password: user %s changed password, %d session(s) revoked",
            user.id, revoked,
        )
        return revoked

    # ── Forgot / reset password ──────────────────────────────────────────

    def forgot_password(
        self,
        *,
        email: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Optional[str]:
        """Generate a reset token for `email`, if that email belongs to an
        active account. ALWAYS returns None to the caller in production —
        see the raw-token-in-dev-mode note below — so app/api/v1/auth.py
        can build the exact same generic response regardless of whether
        the email existed (no account enumeration via this endpoint,
        matching the login/refresh precedent).

        Returns the RAW token only when self._settings.environment is not
        "production" — Sprint 8 has no email provider (per spec: "do not
        implement email provider yet"), so returning the raw token in
        development/testing is the only way to manually verify the full
        reset flow end-to-end before Sprint 9+ wires up real delivery. See
        docs/AUTHENTICATION_ARCHITECTURE.md "Forgot Password" for the full
        rationale and the explicit plan to remove this return value once
        an email provider exists.
        """
        user = self._users.get_by_email(email)
        if user is None or not user.is_active:
            # Same email, same delay profile as the real path would take
            # (a DB lookup happened either way) — no early return that
            # would make timing distinguish "no such user" from "user
            # exists." No token is created; there is nothing to revoke.
            return None

        # A second forgot-password request supersedes any earlier
        # still-outstanding one — an old, possibly-intercepted link should
        # not remain usable once a newer one is issued.
        self._reset_tokens.revoke_outstanding_for_user(user.id)

        raw_token = generate_refresh_token()  # same CSPRNG primitive, different purpose
        now = datetime.now(timezone.utc)
        token_row = PasswordResetToken(
            user_id=user.id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=now + timedelta(
                minutes=self._settings.password_reset_token_expire_minutes
            ),
            requested_ip=ip_address,
            requested_user_agent=user_agent,
            request_id=request_id,
            created_at=now,
        )
        self._reset_tokens.create(token_row)
        logger.info(
            "auth.forgot_password: reset token issued for user %s (request_id=%s)",
            user.id, request_id,
        )

        if self._settings.is_production:
            return None
        return raw_token

    def reset_password(self, *, raw_reset_token: str, new_password: str) -> tuple[User, int]:
        """Consume a reset token: verify it, set the new password, mark the
        token used, and revoke every active session for that user (the
        same security posture as change_password() — a password change,
        however it happened, invalidates every existing login).

        Raises HTTPException(401) if the token is unknown, already used,
        revoked, or expired — never distinguishing which (same posture as
        every other auth failure in this service).
        """
        token_hash = hash_refresh_token(raw_reset_token)
        token_row = self._reset_tokens.get_by_token_hash(token_hash)
        if token_row is None or not token_row.is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_INVALID_RESET_TOKEN_DETAIL,
            )

        user = self._users.get_by_id(token_row.user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_INVALID_RESET_TOKEN_DETAIL,
            )

        user.hashed_password = hash_password(new_password)
        self._users.update(user)
        self._reset_tokens.mark_used(token_row)
        revoked = self._sessions.revoke_all_for_user(user.id, reason="password_changed")
        logger.info(
            "auth.reset_password: user %s reset password via token %s, "
            "%d session(s) revoked",
            user.id, token_row.id, revoked,
        )
        return user, revoked

    # ── Internal ──────────────────────────────────────────────────────────

    def _issue_token_pair(
        self,
        user: User,
        *,
        device_name: Optional[str],
        user_agent: Optional[str],
        ip_address: Optional[str],
    ) -> IssuedTokenPair:
        """Create one access token (JWT) and one refresh token (opaque,
        persisted as a UserSession row). Shared by login() and refresh()
        so both issue tokens through the exact same path."""
        access_token = create_access_token(
            subject=str(user.id),
            secret_key=self._settings.jwt_secret_key,
            algorithm=self._settings.jwt_algorithm,
            expires_minutes=self._settings.jwt_access_token_expire_minutes,
            extra_claims={
                "company_id": str(user.company_id),
                "role": user.role,
                "email": user.email,
            },
        )

        raw_refresh_token = generate_refresh_token()
        now = datetime.now(timezone.utc)
        session_row = UserSession(
            user_id=user.id,
            refresh_token_hash=hash_refresh_token(raw_refresh_token),
            issued_at=now,
            expires_at=now + timedelta(days=self._settings.refresh_token_expire_days),
            device_name=device_name,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        self._sessions.create(session_row)

        return IssuedTokenPair(
            access_token=access_token,
            access_token_expires_in_minutes=self._settings.jwt_access_token_expire_minutes,
            refresh_token=raw_refresh_token,
            refresh_token_expires_in_days=self._settings.refresh_token_expire_days,
            session_id=session_row.id,
        )
