"""
database/models/worker.py — Worker table.

Worker vs User:
    Worker    = a person who appears on construction job sites
    User      = a person who logs into this application

    They are separate because:
    • Most crew members (general laborers, subcontractors) never use the app.
      They appear in daily logs but have no login credentials.
    • A foreman IS both a Worker (appears in logs) and a User (logs in to record).
    • The `user_id` FK on Worker links the two records when the same person
      has both a site presence and an app account.

    This design avoids the anti-pattern of creating User records for every
    crew member (most of whom will never log in), which would bloat the users
    table and complicate authentication.

Subcontractor support:
    Workers may belong to subcontractor companies, not just the main GC.
    `subcontractor_company` (VARCHAR) stores the sub's company name for display.
    In a future Sprint 12 Inventory module, this might become a FK to a
    `subcontractors` table. For now, the string is sufficient and follows
    the ConstructionDailyLog schema field for consistency.

Trade association:
    `trade_id` FK→trades gives each worker a primary trade.
    Workers can appear in any trade on a daily log, but the primary trade
    is used for assignment-level reporting (who is my framing carpenter?).
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, Uuid
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
    from database.models.project import ProjectWorker


class Worker(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, AuditUserMixin, Base):
    """A person who works on construction sites under a company.

    foreman_id in ConstructionDailyLog.project maps to Worker.id.
    worker_identifier in log_trades_on_site is a free-text field from voice
    recordings — it is linked to Worker.id via the repository layer when
    an exact name match is found.
    """

    __tablename__ = "workers"

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        doc="The company that employs or manages this worker.",
    )
    trade_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("trades.id", ondelete="SET NULL"),
        nullable=True,
        doc="Primary trade. A worker may do secondary trades on specific days.",
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        doc="Link to User record if this worker has an app login. NULL for crew-only workers.",
    )

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="laborer",
        doc="Site role: foreman | supervisor | lead | laborer | subcontractor | safety_officer",
    )
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(254), nullable=True)
    subcontractor_company: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        doc="If this worker is from a subcontractor, their company name.",
    )
    license_number: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="Trade license number (electrician, plumber, etc.). Required for licensed trades.",
    )
    license_state: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    emergency_contact_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    emergency_contact_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    company: Mapped["Company"] = relationship("Company", back_populates="workers")
    project_workers: Mapped[list["ProjectWorker"]] = relationship(
        "ProjectWorker", back_populates="worker"
    )

    __table_args__ = (
        Index("ix_workers_company_id", "company_id"),
        Index("ix_workers_trade_id", "trade_id"),
        Index("ix_workers_is_active", "is_active"),
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def __repr__(self) -> str:
        return f"<Worker id={self.id} name={self.full_name!r} role={self.role!r}>"
