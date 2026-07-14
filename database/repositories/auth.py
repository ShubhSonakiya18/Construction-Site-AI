"""
database/repositories/auth.py — UserSessionRepository.

Sprint 8. All refresh-token/session lifecycle operations (issue, look up by
hash, rotate, revoke one, revoke all for a user) live here — routers and
app/core/security.py never touch the user_sessions table directly. See
docs/AUTHENTICATION_ARCHITECTURE.md for the full lifecycle this repository
implements.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from database.models.auth import UserSession
from database.repositories.base import BaseRepository


class UserSessionRepository(BaseRepository[UserSession]):
    """Repository for UserSession (server-side refresh token store).

    Deliberately does NOT inherit soft-delete behavior from BaseRepository
    in any special way — UserSession has no SoftDeleteMixin (see model
    docstring), so BaseRepository's get_by_id()/list() run without the
    deleted_at filter automatically (the isinstance/issubclass checks in
    BaseRepository no-op for non-SoftDeleteMixin models). Active/inactive
    is entirely governed by revoked_at/expires_at, checked explicitly by
    the methods below.
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session, UserSession)

    def get_by_token_hash(self, token_hash: str) -> Optional[UserSession]:
        """Look up a session by its refresh token's SHA-256 hash.

        Returns the row regardless of active/revoked/expired state — callers
        (POST /auth/refresh) decide what to do with an inactive session
        (e.g. reuse-of-a-rotated-token detection, see AUTHENTICATION_ARCHITECTURE.md).
        """
        stmt = select(UserSession).where(UserSession.refresh_token_hash == token_hash)
        return self._session.execute(stmt).scalar_one_or_none()

    def list_active_for_user(self, user_id: UUID) -> list[UserSession]:
        """List every currently-active (not revoked, not expired) session
        for a user — powers a future 'your active sessions' endpoint."""
        now = datetime.now(timezone.utc)
        stmt = (
            select(UserSession)
            .where(UserSession.user_id == user_id)
            .where(UserSession.revoked_at.is_(None))
            .where(UserSession.expires_at > now)
            .order_by(UserSession.issued_at.desc())
        )
        return list(self._session.execute(stmt).scalars().all())

    def revoke(self, session_row: UserSession, *, reason: str) -> UserSession:
        """Revoke a single session. No-op (idempotent) if already revoked —
        the first revocation's reason and timestamp win."""
        if session_row.revoked_at is None:
            session_row.revoked_at = datetime.now(timezone.utc)
            session_row.revoke_reason = reason
            self._session.flush()
        return session_row

    def revoke_all_for_user(self, user_id: UUID, *, reason: str) -> int:
        """Revoke every currently-active session for a user in one
        statement. Returns the number of rows revoked.

        Used by: POST /auth/logout-all (reason='logout_all') and a
        password change (reason='password_changed') — see
        app/services/auth_service.py.
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .where(UserSession.revoked_at.is_(None))
            .values(revoked_at=now, revoke_reason=reason)
        )
        result = self._session.execute(stmt)
        self._session.flush()
        return result.rowcount or 0
