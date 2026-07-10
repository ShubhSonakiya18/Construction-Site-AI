"""
database/mixins.py — Reusable SQLAlchemy column mixins.

Why mixins instead of a single fat base class:
    Composability. Not every table needs every concern:
    • Reference lookup tables (Trade, ConstructionStage) need UUID PK + timestamps
      but NOT soft delete (we never delete a trade type).
    • AuditLog is immutable — no updated_at, no soft delete, no updated_by_id.
    • All mutable business tables (DailyLog, Project, Company) get all four mixins.

    If all concerns lived in one base class, every table would inherit columns
    it doesn't need — a violation of the Interface Segregation Principle.

Mixin design decisions:
    UUIDPrimaryKeyMixin:
        Uses SQLAlchemy's generic Uuid(as_uuid=True) type.
        → PostgreSQL: native UUID column
        → SQLite (tests): CHAR(32) with automatic Python-side uuid.UUID conversion
        default=uuid.uuid4 generates a new UUID at Python level before INSERT,
        so the id is available in Python code immediately after construction
        (no RETURNING clause needed).

    TimestampMixin:
        server_default=func.now() sets the value at the DB server level for
        INSERT. onupdate=func.now() fires at the SQLAlchemy level on UPDATE
        (Python-side). Both are needed: server_default ensures the column is
        never null even on direct SQL inserts that bypass the ORM.

    SoftDeleteMixin:
        deleted_at IS NULL → record is active
        deleted_at IS NOT NULL → record is soft-deleted
        Repositories filter deleted_at IS NULL in all default queries.
        Hard delete (physical removal) is reserved for GDPR right-to-erasure flows
        in Sprint 8 and is not exposed by default repositories.

    AuditUserMixin:
        created_by_id and updated_by_id are plain UUID columns WITHOUT FK
        constraints to avoid circular dependency chains:
            Company → User → Company (company_id FK)
        These UUIDs reference users.id at the application layer.
        Rationale documented in ADR-026 (DECISIONS.md).
        Sprint 8 (Auth) will enforce these at the API boundary.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPrimaryKeyMixin:
    """Adds a UUID v4 primary key column `id` to any model."""

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="UUID v4 primary key. Generated in Python before INSERT so the ID "
            "is available immediately without a DB round-trip.",
    )


class TimestampMixin:
    """Adds `created_at` and `updated_at` audit timestamp columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="UTC timestamp when this record was first created.",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        doc="UTC timestamp of the most recent update to this record.",
    )


class SoftDeleteMixin:
    """Adds soft-delete support via a nullable `deleted_at` column.

    A non-null deleted_at means the record is logically deleted.
    All repository queries filter deleted_at IS NULL by default.
    """

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        doc="UTC timestamp when this record was soft-deleted. "
            "NULL means the record is active.",
    )

    @property
    def is_deleted(self) -> bool:
        """True if this record has been soft-deleted."""
        return self.deleted_at is not None


class AuditUserMixin:
    """Adds `created_by_id` and `updated_by_id` audit UUID columns.

    These reference users.id WITHOUT a FK constraint to avoid circular
    dependency issues at schema creation time (Company ↔ User).
    Integrity is enforced at the repository layer.
    See ADR-026.
    """

    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        default=None,
        doc="UUID of the User who created this record. "
            "No FK constraint — enforced at application layer.",
    )
    updated_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        default=None,
        doc="UUID of the User who last updated this record. "
            "No FK constraint — enforced at application layer.",
    )
