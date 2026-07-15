"""
database/models/company.py — Company and User tables.

Multi-tenancy design:
    The `companies` table is the multi-tenancy root. Every piece of business
    data (projects, daily logs, workers, users) belongs to exactly one company.
    Queries always filter by company_id first, ensuring data isolation between
    tenants.

    Why this design (single-schema multi-tenancy):
    • Simplest to implement — no schema-per-tenant complexity.
    • Works for our scale target (hundreds of companies, not tens of thousands).
    • Sprint 8 (Auth) will add company_id to the JWT payload so every API
      request automatically scopes all queries to the authenticated company.

    Alternative (schema-per-tenant): stronger isolation but requires dynamic
    schema switching — far more complex without proportional benefit at our scale.

User model note:
    `hashed_password` is nullable now — populated in Sprint 8 (Auth).
    `role` is stored as a VARCHAR string, not a SQL ENUM type, so new roles
    can be added with a simple INSERT-to-reference-table, not a migration.
    Valid roles: 'owner', 'admin', 'project_manager', 'foreman',
                 'safety_officer', 'client' (Sprint 8 defines enforcement).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.mixins import (
    AuditUserMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from database.models.project import Project
    from database.models.worker import Worker


class Company(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, AuditUserMixin, Base):
    """A contractor company — the top-level multi-tenant entity.

    Every other business record has a direct or indirect FK to company_id.
    Sprint 8 JWT tokens will embed company_id so all API queries are
    automatically scoped to one company.
    """

    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Legal company name. e.g. 'Apex Residential Construction LLC'",
    )
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        doc="URL-safe identifier. e.g. 'apex-residential'. Sprint 7 uses in API URLs.",
    )
    contact_email: Mapped[Optional[str]] = mapped_column(String(254), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    zip_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False, default="USA")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    subscription_tier: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="trial",
        doc="Billing tier: trial | starter | professional | enterprise",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="company",
        lazy="select",
        doc="All users who belong to this company.",
    )
    projects: Mapped[list["Project"]] = relationship(
        "Project",
        back_populates="company",
        lazy="select",
    )
    workers: Mapped[list["Worker"]] = relationship(
        "Worker",
        back_populates="company",
        lazy="select",
    )

    __table_args__ = (
        Index("ix_companies_slug", "slug"),
        Index("ix_companies_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Company id={self.id} name={self.name!r}>"


class User(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, AuditUserMixin, Base):
    """An application user. Can be a foreman, project manager, admin, or client.

    Relationship to Worker: a Worker represents a person on a job site.
    A User represents a person who logs into the application. Some workers
    have user accounts (foresmen), others don't (subcontractors).
    The `worker_id` FK links the two when the same person appears in both.

    Password: hashed_password is populated in Sprint 8. Null until then.
    Role: stored as string, not SQL ENUM — adding new roles needs no migration.
    """

    __tablename__ = "users"

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        doc="The company this user belongs to. Never null — every user belongs to a company.",
    )
    email: Mapped[str] = mapped_column(
        String(254),
        unique=True,
        nullable=False,
        doc="Email address used for login. Must be globally unique across all companies.",
    )
    hashed_password: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="Bcrypt hash of the user's password. Populated in Sprint 8 (Auth).",
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="foreman",
        doc="User role: owner | admin | project_manager | foreman | "
            "safety_officer | client. Sprint 8 enforces role-based access.",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    worker_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("workers.id", ondelete="SET NULL"),
        nullable=True,
        doc="Links this user to their Worker record if they appear on job sites.",
    )

    # ── Account lockout (Sprint 8, Subsystem 5 — Security Hardening) ────────
    # Additive columns on the frozen Sprint 6 User model — see ADR entry
    # in docs/DECISIONS.md for why these live directly on User rather than
    # a separate table: the counter's lifecycle is 1:1 with one User row
    # (reset on success, incremented on failure), unlike UserSession
    # (Subsystem 1) which is genuinely one-to-many per user.
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Consecutive failed login attempts since the last success. "
            "Reset to 0 on successful login or password reset.",
    )
    locked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="NULL means not locked. A future timestamp means login is "
            "rejected (423) until this time passes. Cleared by admin "
            "unlock, a successful login after expiry, or a password reset.",
    )
    last_failed_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp of the most recent failed login attempt — audit/"
            "debugging aid, not itself used in lockout logic (that's "
            "failed_login_attempts + locked_until).",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    company: Mapped["Company"] = relationship("Company", back_populates="users")

    __table_args__ = (
        Index("ix_users_company_id", "company_id"),
        Index("ix_users_email", "email"),
        Index("ix_users_role", "role"),
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"
