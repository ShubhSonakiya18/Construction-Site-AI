"""
database/models/password_reset.py — PasswordResetToken: single-use, short-lived
password reset credential store.

Sprint 8. Additive — a new table, no existing table modified. See
docs/AUTHENTICATION_ARCHITECTURE.md "Forgot Password" for the full lifecycle.

Why a dedicated table, not a JWT:
    A JWT encoding {user_id, purpose: "password_reset", exp} would need no
    migration, but it can't be made single-use or explicitly revocable
    without a second, parallel table tracking "which reset JWTs have
    already been consumed" — at which point we've built this table anyway,
    just with extra signature-verification overhead on top. A dedicated
    table gets single-use (used_at) and revocability (revoked_at) for free,
    with the same hash-only storage discipline as UserSession
    (database/models/auth.py) — see that model's docstring for why we
    store a hash, never the raw token.

Why this is a SEPARATE table from user_sessions, not a shared "tokens"
table with a type discriminator:
    A refresh token and a reset token have different lifecycles (a refresh
    token is meant to be used repeatedly via rotation; a reset token is
    used exactly once and then permanently dead) and different lifetimes
    (30 days vs. 30 minutes by default). Modeling them as one polymorphic
    table would mean every query needs a WHERE token_type = '...' filter
    and every column not shared by both purposes (rotated_from_id vs.
    used_at) would need to be nullable for the other type — two focused
    tables are simpler to reason about and to index than one table wearing
    two hats.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from database.models.company import User


class PasswordResetToken(UUIDPrimaryKeyMixin, Base):
    """One row per requested password reset.

    Lifecycle:
        created — POST /auth/forgot-password generates a token, stores its
                  hash here, and (development environment only — see
                  Settings.is_production) returns the raw token in the
                  response body since no email provider exists yet.
        used    — POST /auth/reset-password successfully consumes it:
                  used_at is set, the user's password is changed, and
                  every active UserSession for that user is revoked.
        expired — expires_at has passed; treated as invalid but the row is
                  not deleted (audit trail).
        revoked — an explicit invalidation before use (e.g. a second
                  forgot-password request for the same user revokes any
                  still-outstanding prior token — see AuthService — so an
                  old, possibly-intercepted email link stops working the
                  moment a newer one is requested).

    A token is valid to consume iff: used_at IS NULL AND revoked_at IS NULL
    AND expires_at > now(). All three are checked on every
    POST /auth/reset-password call.
    """

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        doc="The user this reset token was issued for.",
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        doc="SHA-256 hex digest of the raw reset token. Never the raw "
            "value — same discipline as UserSession.refresh_token_hash.",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        doc="Short-lived by design (default 30 minutes, "
            "Settings.password_reset_token_expire_minutes) — a reset link "
            "sitting in an inbox for days is a standing risk.",
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="NULL until consumed. Non-null makes this token permanently "
            "dead even if expires_at hasn't passed yet — single-use.",
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Set when a newer reset request supersedes this one, before "
            "this token was ever used.",
    )
    requested_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    requested_user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        doc="The X-Request-ID (app/middleware/request_id.py) of the "
            "POST /auth/forgot-password call that created this row — "
            "correlates this row to the structured request log line.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        doc="When this reset was requested. No TimestampMixin — see "
            "UserSession's docstring for the same reasoning "
            "(no updated_at needed; used_at/revoked_at already carry "
            "distinct meaning).",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        Index("ix_password_reset_tokens_user_id", "user_id"),
        Index("ix_password_reset_tokens_token_hash", "token_hash"),
        Index("ix_password_reset_tokens_expires_at", "expires_at"),
    )

    @property
    def is_valid(self) -> bool:
        """True iff this token can currently be consumed.

        See UserSession.is_active (database/models/auth.py) for why
        expires_at is normalized to UTC before comparison — SQLite
        (tests) does not preserve tzinfo on read-back; PostgreSQL
        (production) does. Every write path stores UTC, so treating a
        naive read-back as UTC is correct in both cases.
        """
        from datetime import timezone as _tz
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=_tz.utc)
        now = datetime.now(_tz.utc)
        return self.used_at is None and self.revoked_at is None and expires_at > now

    def __repr__(self) -> str:
        state = "valid" if self.is_valid else "invalid"
        return f"<PasswordResetToken id={self.id} user_id={self.user_id} {state}>"
