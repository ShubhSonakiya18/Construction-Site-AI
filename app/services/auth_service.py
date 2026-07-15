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
from app.core.rate_limit import RateLimiter
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.services.audit_helpers import safe_log_event
from database.models.auth import UserSession
from database.models.company import User
from database.models.password_reset import PasswordResetToken
from database.repositories.auth import UserSessionRepository
from database.repositories.company import UserRepository
from database.repositories.generation import AuditLogRepository
from database.repositories.password_reset import PasswordResetTokenRepository

logger = logging.getLogger("app.auth")

_INVALID_CREDENTIALS_DETAIL = "Incorrect email or password."
_INVALID_REFRESH_DETAIL = "Invalid or expired refresh token."
_INVALID_RESET_TOKEN_DETAIL = "Invalid, expired, or already-used reset token."
_GENERIC_FORGOT_PASSWORD_MESSAGE = "If that email is registered, a reset link has been sent."
_ACCOUNT_LOCKED_DETAIL = "Account temporarily locked due to repeated failed login attempts."
_RATE_LIMITED_DETAIL = "Too many attempts. Please try again later."


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

    def __init__(
        self, session: Session, settings: Settings, *, rate_limiter: Optional[RateLimiter] = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._users = UserRepository(session)
        self._sessions = UserSessionRepository(session)
        self._reset_tokens = PasswordResetTokenRepository(session)
        self._audit = AuditLogRepository(session)
        # Optional — callers that don't pass one (e.g. existing tests
        # written before Subsystem 5) get no rate limiting rather than a
        # constructor error, since rate limiting is an additive hardening
        # layer, not a change to the core login contract.
        self._rate_limiter = rate_limiter

    # ── Login ─────────────────────────────────────────────────────────────

    def login(
        self,
        *,
        email: str,
        password: str,
        device_name: Optional[str] = None,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> tuple[User, IssuedTokenPair]:
        """Verify credentials and issue a new access + refresh token pair.

        Raises HTTPException(401) for any credential failure — wrong
        password, nonexistent email, or inactive account — all with the
        same message (see app/api/v1/auth.py's original Sprint 7
        docstring: account enumeration prevention, unchanged here).

        Raises HTTPException(429) if the coarse per-email rate limit
        (Settings.rate_limit_login_attempts) has been exceeded — a
        backstop layered ABOVE the per-account lockout below, catching
        e.g. a burst of requests against many different emails from one
        attacker that no single account's lockout counter would see.

        Raises HTTPException(423) if the account is currently locked —
        see _check_and_apply_lockout() for the full lockout state machine
        (5 failures / 15 min lockout, configurable via Settings).
        """
        if self._rate_limiter is not None and not self._rate_limiter.check(
            f"login:{email}",
            limit=self._settings.rate_limit_login_attempts,
            window_seconds=self._settings.rate_limit_login_window_seconds,
        ):
            safe_log_event(
                self._audit, "security.rate_limit_triggered",
                ip_address=ip_address, request_id=request_id, success=False,
                metadata={"scope": "login", "key": email},
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=_RATE_LIMITED_DETAIL,
            )

        user = self._users.get_by_email(email)

        if user is not None and self._is_locked(user):
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=_ACCOUNT_LOCKED_DETAIL,
            )

        if user is None or not user.is_active or not verify_password(
            password, user.hashed_password or ""
        ):
            if user is not None:
                self._record_failed_login(user, request_id=request_id, ip_address=ip_address)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=_INVALID_CREDENTIALS_DETAIL,
            )

        self._reset_lockout(user)
        user.last_login_at = datetime.now(timezone.utc)
        self._users.update(user)

        pair = self._issue_token_pair(
            user, device_name=device_name, user_agent=user_agent, ip_address=ip_address
        )
        safe_log_event(
            self._audit, "user.login",
            entity_type="user", entity_id=user.id,
            actor_id=user.id, company_id=user.company_id,
            ip_address=ip_address, user_agent=user_agent,
            request_id=request_id, success=True,
            metadata={"session_id": str(pair.session_id)},
        )
        return user, pair

    # ── Refresh ───────────────────────────────────────────────────────────

    def refresh(
        self,
        *,
        raw_refresh_token: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
        request_id: Optional[str] = None,
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
                safe_log_event(
                    self._audit, "auth.invalid_refresh_token",
                    entity_type="user_session", entity_id=session_row.id,
                    actor_id=session_row.user_id,
                    ip_address=ip_address, user_agent=user_agent,
                    request_id=request_id, success=False,
                    metadata={"reason": "reuse_of_revoked_session", "revoke_reason": session_row.revoke_reason},
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
        safe_log_event(
            self._audit, "auth.refresh_token_revoked",
            entity_type="user_session", entity_id=session_row.id,
            actor_id=user.id, company_id=user.company_id,
            ip_address=ip_address, user_agent=user_agent,
            request_id=request_id, success=True,
            metadata={"reason": "rotated"},
        )

        pair = self._issue_token_pair(
            user,
            device_name=session_row.device_name,
            user_agent=user_agent or session_row.user_agent,
            ip_address=ip_address or session_row.ip_address,
        )
        safe_log_event(
            self._audit, "auth.refresh_token_issued",
            entity_type="user_session", entity_id=pair.session_id,
            actor_id=user.id, company_id=user.company_id,
            ip_address=ip_address, user_agent=user_agent,
            request_id=request_id, success=True,
        )
        return user, pair

    # ── Logout ────────────────────────────────────────────────────────────

    def logout(
        self, *, raw_refresh_token: str,
        ip_address: Optional[str] = None, user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> UUID:
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
        safe_log_event(
            self._audit, "user.logout",
            entity_type="user_session", entity_id=session_row.id,
            actor_id=session_row.user_id,
            ip_address=ip_address, user_agent=user_agent,
            request_id=request_id, success=True,
        )
        return session_row.id

    def logout_all(
        self, *, user_id: UUID,
        ip_address: Optional[str] = None, user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> int:
        """Revoke every active session for a user. Returns the count revoked."""
        revoked = self._sessions.revoke_all_for_user(user_id, reason="logout_all")
        safe_log_event(
            self._audit, "user.logout_all",
            entity_type="user", entity_id=user_id,
            actor_id=user_id,
            ip_address=ip_address, user_agent=user_agent,
            request_id=request_id, success=True,
            metadata={"sessions_revoked": revoked},
        )
        return revoked

    # ── Password change ──────────────────────────────────────────────────

    def change_password(
        self, *, user: User, current_password: str, new_password: str,
        ip_address: Optional[str] = None, user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
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
            safe_log_event(
                self._audit, "user.password_change_failed",
                entity_type="user", entity_id=user.id,
                actor_id=user.id, company_id=user.company_id,
                ip_address=ip_address, user_agent=user_agent,
                request_id=request_id, success=False,
            )
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
        safe_log_event(
            self._audit, "user.password_changed",
            entity_type="user", entity_id=user.id,
            actor_id=user.id, company_id=user.company_id,
            ip_address=ip_address, user_agent=user_agent,
            request_id=request_id, success=True,
            metadata={"sessions_revoked": revoked},
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

        Raises HTTPException(429) if this email has exceeded
        Settings.rate_limit_forgot_password_attempts within the
        configured window — checked BEFORE the user lookup, and keyed
        purely on the submitted email regardless of whether it exists,
        so the rate limit itself can't be used as an oracle (an
        unlimited-attempts nonexistent email would otherwise never
        trip it, while a real one would — that difference would leak
        exactly the information this endpoint's generic response is
        designed to hide).
        """
        if self._rate_limiter is not None and not self._rate_limiter.check(
            f"forgot_password:{email}",
            limit=self._settings.rate_limit_forgot_password_attempts,
            window_seconds=self._settings.rate_limit_forgot_password_window_seconds,
        ):
            safe_log_event(
                self._audit, "security.rate_limit_triggered",
                ip_address=ip_address, request_id=request_id, success=False,
                metadata={"scope": "forgot_password", "key": email},
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=_RATE_LIMITED_DETAIL,
            )

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
        # Only logged when a real token was actually created for a real,
        # active user — see the "no early return" note above: logging an
        # event on the nonexistent-email path too would itself become an
        # enumeration side channel (an attacker could infer "this email
        # exists" purely from whether an audit row for it appears),
        # exactly what this method's identical-response design prevents
        # at the HTTP layer.
        safe_log_event(
            self._audit, "user.password_reset_requested",
            entity_type="user", entity_id=user.id,
            actor_id=user.id, company_id=user.company_id,
            ip_address=ip_address, user_agent=user_agent,
            request_id=request_id, success=True,
        )

        if self._settings.is_production:
            return None
        return raw_token

    def reset_password(
        self, *, raw_reset_token: str, new_password: str,
        ip_address: Optional[str] = None, user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> tuple[User, int]:
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
        self._reset_lockout(user)  # explicit requirement: "Password reset clears the lockout"
        self._users.update(user)
        self._reset_tokens.mark_used(token_row)
        revoked = self._sessions.revoke_all_for_user(user.id, reason="password_changed")
        logger.info(
            "auth.reset_password: user %s reset password via token %s, "
            "%d session(s) revoked",
            user.id, token_row.id, revoked,
        )
        safe_log_event(
            self._audit, "user.password_reset_completed",
            entity_type="user", entity_id=user.id,
            actor_id=user.id, company_id=user.company_id,
            ip_address=ip_address, user_agent=user_agent,
            request_id=request_id, success=True,
            metadata={"sessions_revoked": revoked},
        )
        return user, revoked

    # ── Account lockout (Sprint 8, Subsystem 5) ──────────────────────────

    def unlock_user(
        self, *, user: User, actor_id: UUID, request_id: Optional[str] = None,
    ) -> User:
        """Admin unlock: clear a lock before it would naturally expire.
        Distinct from _reset_lockout() only in that this one is always
        externally triggered and always audited as an explicit action —
        _reset_lockout() is an internal side effect of a successful login
        or password reset, not a standalone administrative act."""
        user.failed_login_attempts = 0
        user.locked_until = None
        self._users.update(user)
        safe_log_event(
            self._audit, "user.unlocked",
            entity_type="user", entity_id=user.id,
            actor_id=actor_id, target_user_id=user.id, company_id=user.company_id,
            request_id=request_id, success=True,
        )
        logger.info("auth.unlock_user: user %s unlocked by actor %s", user.id, actor_id)
        return user

    def _is_locked(self, user: User) -> bool:
        if user.locked_until is None:
            return False
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            # See database/models/auth.py UserSession.is_active for why
            # this normalization is needed: SQLite (tests) doesn't
            # preserve tzinfo on DateTime(timezone=True) read-back,
            # PostgreSQL does — every write path here stores UTC, so a
            # naive read-back is safely treated as UTC.
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until <= datetime.now(timezone.utc):
            return False  # lock has naturally expired — "Automatic unlock after timeout"
        return True

    def _record_failed_login(
        self, user: User, *, request_id: Optional[str], ip_address: Optional[str],
    ) -> None:
        """Increment the failure counter and lock the account if the
        configured threshold is reached. Called only for a genuine wrong
        password against an existing, active account — not for a
        nonexistent email (there is no User row to record a failure
        against, and doing so would itself be an enumeration side
        channel: an attacker could infer "this account now has N failed
        attempts" only by controlling N through valid emails).

        Commits immediately, before returning to login()'s caller, which
        raises HTTPException(401) right after this returns. The request-
        scoped session (database/session.py:get_session(), and its test
        mirror in tests/conftest_api.py) rolls back on ANY exception —
        including an intentionally-raised HTTPException for a wrong
        password — which would otherwise silently discard this exact
        increment on every single failed attempt, making lockout
        permanently unreachable. This was a real bug, caught by
        test_api_security_hardening.py's lockout tests (5 failed attempts
        never actually persisted past 0). Committing here, in a small
        sub-transaction scoped to just this state change, is the fix —
        the audit log entries below are part of the same commit.
        """
        now = datetime.now(timezone.utc)
        user.failed_login_attempts += 1
        user.last_failed_login_at = now

        just_locked = False
        if user.failed_login_attempts >= self._settings.lockout_max_failed_attempts:
            user.locked_until = now + timedelta(minutes=self._settings.lockout_duration_minutes)
            just_locked = True

        self._users.update(user)

        self._audit.log_event(
            "user.login_failed",
            entity_type="user",
            entity_id=user.id,
            actor_id=user.id,
            company_id=user.company_id,
            ip_address=ip_address,
            request_id=request_id,
            success=False,
            metadata={"failed_attempts": user.failed_login_attempts},
        )
        if just_locked:
            self._audit.log_event(
                "user.locked",
                entity_type="user",
                entity_id=user.id,
                actor_id=user.id,
                company_id=user.company_id,
                ip_address=ip_address,
                request_id=request_id,
                success=True,
                metadata={"locked_until": user.locked_until.isoformat()},
            )
            logger.warning(
                "auth.login: user %s locked until %s after %d failed attempts",
                user.id, user.locked_until, user.failed_login_attempts,
            )

        self._session.commit()

    def _reset_lockout(self, user: User) -> None:
        user.failed_login_attempts = 0
        user.locked_until = None

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
