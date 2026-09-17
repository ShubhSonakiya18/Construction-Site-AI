"""
database/models/alerts.py — ProjectAlertSent: Sprint 19.

One row per (project_id, alert_type), tracking the last time a real alert
email was sent and what status it was sent for. This is NOT an append-only
audit log of every alert ever sent -- it answers "when did we last alert on
this, and was it a real change or the same bad status persisting," which is
exactly what app/services/alert_service.py's dedup decision needs and what
Deliverable 4's optional alert-history view reads from. See ADR-066 for why
this shape (a per-(project, type) last-sent row) was chosen over diffing
the previous vs. current computed status on every scheduler tick alone.

alert_type is a plain string, not a SQL ENUM, matching User.role's own
documented convention (database/models/company.py) -- adding a third alert
type later needs no migration.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from database.models.project import Project


class ProjectAlertSent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tracks the last alert sent for one (project, alert_type) pair.

    last_status_value is the computed status string the alert fired for
    (e.g. "over_budget", "approaching_budget") -- app/services/alert_service.py
    compares this against the newly computed status on each tick: a real
    transition always fires regardless of cooldown (worse news is never
    suppressed by a timer), while the same status re-fires only after
    last_sent_at is older than the cooldown window (ADR-066).
    """

    __tablename__ = "project_alerts_sent"
    __table_args__ = (
        UniqueConstraint("project_id", "alert_type", name="uq_project_alert_type"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        doc="The project this alert was sent for.",
    )
    alert_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        doc="'budget_variance' | 'safety_warning' — see app/services/alert_service.py.",
    )
    last_status_value: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        doc="The computed status string this alert last fired for, e.g. "
            "'over_budget' or 'approaching_budget'.",
    )
    last_sent_at: Mapped[datetime] = mapped_column(
        nullable=False,
        doc="When the last real alert email for this (project, alert_type) "
            "pair was sent. Compared against the cooldown window on each "
            "scheduler tick.",
    )

    project: Mapped["Project"] = relationship("Project")
