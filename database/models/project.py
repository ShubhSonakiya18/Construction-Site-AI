"""
database/models/project.py — Project, Site, and ProjectWorker tables.

Project hierarchy:
    Company → 1:N Projects → 1:N Sites
    A company can have many concurrent projects.
    A project can span multiple physical sites (e.g., a multi-building development).
    Each daily log is tied to a project and optionally a specific site.

ProjectWorker (junction table):
    Tracks which workers are assigned to which projects.
    This is separate from daily log presence (log_trades_on_site) because:
    • A foreman needs to know their project assignment before day 1.
    • Queries like "who is on project X?" shouldn't require scanning daily logs.
    • Future Sprint 11 scheduling module needs to know who is contracted per project.

Project status lifecycle:
    planning → active → paused → completed | cancelled
    Managed at the application layer (repository) — not a DB enum.

Why `client_name` is denormalized on Project:
    A client person/organisation may appear across multiple projects.
    A proper normalised design would have a `clients` table. However:
    • At the scale of Sprint 6-8, a single string is sufficient.
    • Adding a `clients` table is straightforward in Sprint 11 without breaking
      the existing schema (Project.client_name stays as a fallback).
    This is a documented, conscious denormalization.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.mixins import (
    AuditUserMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from database.models.company import Company
    from database.models.worker import Worker
    from database.models.audio import AudioFile
    from database.models.daily_log import DailyLog


class Project(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, AuditUserMixin, Base):
    """A construction project — the primary grouping for daily logs and site activity.

    project_id in ConstructionDailyLog.project maps to this table's id.
    """

    __tablename__ = "projects"

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Human-readable project name. e.g. 'Johnson Residence — 123 Oak Street'",
    )
    project_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="residential_single_family | residential_multi_family | "
            "commercial_small | renovation | addition | other",
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="planning",
        doc="Lifecycle state: planning | active | paused | completed | cancelled",
    )

    # ── Client info (conscious denormalization — see module docstring) ─────────
    client_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    client_contact_email: Mapped[Optional[str]] = mapped_column(String(254), nullable=True)
    client_contact_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    contractor_company: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # ── Dimensions and schedule ───────────────────────────────────────────────
    project_size_sqft: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    project_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    planned_completion_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    actual_completion_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    contract_value_usd: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    permit_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    company: Mapped["Company"] = relationship("Company", back_populates="projects")
    sites: Mapped[list["Site"]] = relationship(
        "Site", back_populates="project", cascade="all, delete-orphan"
    )
    project_workers: Mapped[list["ProjectWorker"]] = relationship(
        "ProjectWorker", back_populates="project", cascade="all, delete-orphan"
    )
    audio_files: Mapped[list["AudioFile"]] = relationship(
        "AudioFile", back_populates="project"
    )
    daily_logs: Mapped[list["DailyLog"]] = relationship(
        "DailyLog", back_populates="project"
    )

    __table_args__ = (
        Index("ix_projects_company_id", "company_id"),
        Index("ix_projects_status", "status"),
        Index("ix_projects_company_status", "company_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Project id={self.id} name={self.name!r} status={self.status!r}>"


class Site(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A physical construction site location.

    A project may have one or more sites. Most residential projects have one.
    Multi-building developments (townhomes, duplexes) may have multiple.

    The primary site is marked with is_primary=True.
    Daily logs reference site_id to tie activity to a specific location.

    Latitude/longitude enable future GPS-based site verification and
    the mapping features planned in Sprint 13 Analytics Dashboard.
    """

    __tablename__ = "sites"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    zip_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False, default="USA")
    latitude: Mapped[Optional[float]] = mapped_column(
        Numeric(9, 6),
        nullable=True,
        doc="GPS latitude — used by future mapping and GPS verification features.",
    )
    longitude: Mapped[Optional[float]] = mapped_column(
        Numeric(9, 6),
        nullable=True,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        doc="True for the main site. Projects with multiple sites mark exactly one primary.",
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    project: Mapped["Project"] = relationship("Project", back_populates="sites")
    daily_logs: Mapped[list["DailyLog"]] = relationship("DailyLog", back_populates="site")

    __table_args__ = (
        Index("ix_sites_project_id", "project_id"),
    )

    def __repr__(self) -> str:
        return f"<Site id={self.id} address={self.address!r}>"


class ProjectWorker(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Junction table: which workers are assigned to which projects.

    Separate from log_trades_on_site (daily presence) because:
    • Assignment is a contract-level fact, known before day 1.
    • Daily presence is a logged fact, recorded each evening.
    • Queries like 'all workers on project X' hit this table, not daily logs.

    One worker can be assigned to many projects (e.g., a subcontractor
    working across multiple sites). One project has many assigned workers.
    """

    __tablename__ = "project_workers"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    worker_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workers.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_on_project: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="worker",
        doc="The worker's role on this specific project: foreman | supervisor | "
            "subcontractor | laborer | safety_officer",
    )
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
        doc="NULL means the worker is still active on this project.",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    project: Mapped["Project"] = relationship("Project", back_populates="project_workers")
    worker: Mapped["Worker"] = relationship("Worker", back_populates="project_workers")

    __table_args__ = (
        UniqueConstraint("project_id", "worker_id", name="uq_project_workers"),
        Index("ix_project_workers_project_id", "project_id"),
        Index("ix_project_workers_worker_id", "worker_id"),
    )

    def __repr__(self) -> str:
        return f"<ProjectWorker project={self.project_id} worker={self.worker_id}>"
