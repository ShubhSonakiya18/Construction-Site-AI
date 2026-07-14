"""
database/repositories/password_reset.py — PasswordResetTokenRepository.

Sprint 8. Mirrors database/repositories/auth.py's shape — see that file's
docstring for the general pattern this follows.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from database.models.password_reset import PasswordResetToken
from database.repositories.base import BaseRepository


class PasswordResetTokenRepository(BaseRepository[PasswordResetToken]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, PasswordResetToken)

    def get_by_token_hash(self, token_hash: str) -> Optional[PasswordResetToken]:
        """Look up a reset token by its SHA-256 hash, regardless of
        used/revoked/expired state — callers decide what to do with an
        invalid one (see PasswordResetToken.is_valid)."""
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def revoke_outstanding_for_user(self, user_id: UUID) -> int:
        """Revoke every still-valid (not used, not expired, not already
        revoked) reset token for a user. Called at the start of a new
        forgot-password request so an old, possibly-intercepted reset link
        stops working the moment a newer one is issued. Returns the count
        revoked."""
        now = datetime.now(timezone.utc)
        stmt = (
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id)
            .where(PasswordResetToken.used_at.is_(None))
            .where(PasswordResetToken.revoked_at.is_(None))
            .where(PasswordResetToken.expires_at > now)
            .values(revoked_at=now)
        )
        result = self._session.execute(stmt)
        self._session.flush()
        return result.rowcount or 0

    def mark_used(self, token_row: PasswordResetToken) -> PasswordResetToken:
        """Mark a token consumed. Idempotent — the first consumption wins."""
        if token_row.used_at is None:
            token_row.used_at = datetime.now(timezone.utc)
            self._session.flush()
        return token_row
