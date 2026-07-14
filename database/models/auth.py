"""
database/models/auth.py — UserSession: server-side refresh-token/session store.

Sprint 8. Additive to the Sprint 6 schema — a new table, no existing table
modified. See docs/AUTHENTICATION_ARCHITECTURE.md for the full session
lifecycle (issue, rotate, revoke) and why a database-backed session store
was chosen over a stateless-JWT-only refresh token.

Why this is a separate table from `users`, not columns on User:
    A user can be logged in from multiple devices simultaneously (phone +
    laptop, or two browser tabs). Each login is one row here, not one
    column on User — otherwise "logout all devices" would need to encode
    an unbounded list of active refresh tokens into a fixed number of User
    columns, and "logout this device only" would be unrepresentable.

Why we store a hash, never the raw refresh token:
    Same threat model as a password: this table is a credential store. If
    the database were ever exfiltrated, a raw refresh token is a live
    Bearer credential an attacker can use immediately — a SHA-256 hash is
    not (the raw token can't be recovered from it, and unlike a password,
    a refresh token is already high-entropy random data, so a fast hash
    without bcrypt's deliberate slowness is correct here: we are not
    defending against low-entropy user-chosen input, we are defending
    against database exfiltration of an unguessable secret).

Why every field the spec asked for (device_name, user_agent, ip_address,
revoke_reason) rather than just token_hash + expiry:
    This table doubles as the audit trail for "Session Management" in the
    spec — a user (or a future admin panel) needs to see "Chrome on
    Windows, IP 1.2.3.4, last used 3 minutes ago" to make an informed
    decision about which sessions to revoke. revoke_reason distinguishes
    an ordinary logout from a password-change-triggered mass revocation or
    a future admin-initiated one — useful both for the user-facing session
    list and for audit logging (see database/models/audit.py, Subsystem 7).
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


class UserSession(UUIDPrimaryKeyMixin, Base):
    """One row per issued refresh token — i.e. one row per logged-in device/session.

    Lifecycle:
        created  — POST /auth/login or POST /auth/refresh issues a new
                   refresh token and inserts this row.
        rotated  — POST /auth/refresh revokes THIS row (revoked_at set,
                   revoke_reason="rotated") and inserts a new row for the
                   replacement token. The old token_hash is never reused.
        revoked  — POST /auth/logout (this session only), POST
                   /auth/logout-all (every session for this user), or a
                   password change (every session for this user) sets
                   revoked_at + revoke_reason on existing rows.

    A session is valid iff: revoked_at IS NULL AND expires_at > now().
    Both conditions are checked on every POST /auth/refresh call.

    Deliberately NOT using TimestampMixin/SoftDeleteMixin:
        TimestampMixin's updated_at (auto-touched on any column change)
        would fire on every last_used_at bump, which is not useful audit
        information here — we track issued_at/expires_at/revoked_at
        explicitly instead, each with a distinct meaning. SoftDeleteMixin's
        deleted_at would be a second, redundant "is this inactive" signal
        alongside revoked_at — one column for that state, not two. Rows
        are never deleted (soft or hard) by normal operation; a future
        Sprint 10+ retention job may hard-delete rows past some age purely
        for table size, which is a housekeeping concern, not a business
        state — see AUTHENTICATION_ARCHITECTURE.md "Retention" note.
    """

    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        doc="The user this session/refresh token belongs to. CASCADE: if a "
            "user row is ever hard-deleted (GDPR erasure), their sessions "
            "go with them — a session for a nonexistent user is meaningless.",
    )
    refresh_token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        doc="SHA-256 hex digest (64 chars) of the raw refresh token. Never "
            "the raw token itself — see module docstring.",
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        doc="When this refresh token was issued (login or rotation).",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        doc="Absolute expiry — this session cannot be refreshed past this "
            "point even if never explicitly revoked.",
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp of the most recent successful POST /auth/refresh "
            "using this session's token. NULL if never refreshed since issue.",
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="NULL means active. Non-null means this session can no longer "
            "be used to refresh, regardless of expires_at.",
    )
    revoke_reason: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="One of: 'logout' | 'logout_all' | 'rotated' | "
            "'password_changed' | 'admin_revoked'. NULL while active.",
    )
    device_name: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        doc="Client-supplied human-readable label (e.g. 'Sarah's iPhone'). "
            "Optional — a client that doesn't send one just gets a blank "
            "label in the session list.",
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="Raw User-Agent header captured at login/refresh time.",
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        doc="Client IP at login time. 45 chars fits a full IPv6 address.",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        Index("ix_user_sessions_user_id", "user_id"),
        Index("ix_user_sessions_refresh_token_hash", "refresh_token_hash"),
        Index("ix_user_sessions_expires_at", "expires_at"),
    )

    @property
    def is_active(self) -> bool:
        """True iff this session can currently be used to refresh.

        SQLite (used in tests) does not preserve tzinfo on DateTime(timezone=True)
        columns — a value written as timezone-aware reads back naive. PostgreSQL
        (production) does not have this problem: TIMESTAMPTZ round-trips as
        aware. Rather than let this be a SQLite-only test flake, expires_at is
        treated as UTC whenever it comes back naive — correct in both cases,
        since every write path in this codebase (AuthService, migrations) only
        ever stores UTC.
        """
        from datetime import timezone
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return self.revoked_at is None and expires_at > now

    def __repr__(self) -> str:
        status = "active" if self.is_active else "inactive"
        return f"<UserSession id={self.id} user_id={self.user_id} {status}>"
