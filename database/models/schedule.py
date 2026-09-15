"""
database/models/schedule.py — ProjectSchedule and ScheduleTask: Sprint 11.

Two tables, following the same parent/child normalization pattern DailyLog
already uses (one parent row, child rows for the repeating structure):

    project_schedules — one row per project. Sprint 11 scope is exactly one
        active schedule per project (see docs/NEXT_SPRINT.md Deliverable 1 —
        multiple schedule revisions/replanning history is explicitly out of
        scope; a UniqueConstraint on project_id enforces this at the DB
        level rather than leaving it as an application-layer convention).

    schedule_tasks — one row per stage/task within that schedule. `stage_id`
        matches a node id in knowledge/dependency_graph.json (e.g.
        "foundation", "framing") — that file is the authoritative source for
        the generic/typical construction sequence and critical path; this
        table stores the per-project instantiation of it (planned dates,
        actual dates as they come in from approved daily logs, and whether
        this task sits on THIS project's critical path, which Deliverable 5
        computes from planned durations and may differ from the generic
        typical_total_days in dependency_graph.json).

is_on_critical_path on ScheduleTask is seeded from a per-project CPM
computation at schedule-creation time (Deliverable 5), not copied verbatim
from dependency_graph.json's generic critical path — a project whose planned
durations differ from "typical" can have a different critical path.

LogWorkItem.linked_schedule_task_id (database/models/log_items.py) is a
plain nullable string column with no FK constraint today. This migration
does NOT add a FK constraint from LogWorkItem to ScheduleTask — see the
migration's own docstring for why (existing rows would need a backfill,
and the column predates this table existing at all). The link stays soft;
resolving it is left as a documented follow-up (ADR pending) rather than a
Sprint 11 requirement, since nothing in this sprint's 7 deliverables
actually needs to join through it.
"""
from __future__ import annotations

import uuid
from datetime import date as date_type
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
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
    from database.models.project import Project


class ProjectSchedule(UUIDPrimaryKeyMixin, TimestampMixin, AuditUserMixin, Base):
    """The single active schedule for a project.

    Sprint 11 scope: exactly one schedule per project (UniqueConstraint on
    project_id below). No soft delete — a schedule that's no longer wanted
    is a real design question (replace it? archive it?) that Sprint 11
    deliberately defers per docs/NEXT_SPRINT.md's out-of-scope list; adding
    SoftDeleteMixin now would imply an answer that hasn't been decided.
    """

    __tablename__ = "project_schedules"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        doc="One schedule per project — Sprint 11 scope excludes multiple "
            "schedule revisions/replanning history.",
    )
    schedule_start_date: Mapped[date_type] = mapped_column(
        Date,
        nullable=False,
        doc="The date this schedule's planned dates are computed from — "
            "normally Project.project_start_date at schedule-creation time.",
    )
    critical_path_total_days: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="The project's total planned span in days, from the "
            "Deliverable 5 CPM pass — the latest planned_end_date offset "
            "across all tasks, which already accounts for any inter-task "
            "lag (e.g. concrete cure time) and is NOT simply the sum of "
            "critical-path task durations. NULL until that computation "
            "has run once.",
    )
    projected_completion_date: Mapped[Optional[date_type]] = mapped_column(
        Date,
        nullable=True,
        doc="schedule_start_date + critical_path_total_days, recomputed "
            "whenever Deliverable 6's delay-impact propagation runs. Starts "
            "equal to the CPM-derived date; shifts later as critical-path "
            "delays are recorded.",
    )

    project: Mapped["Project"] = relationship("Project", back_populates="schedule")
    tasks: Mapped[list["ScheduleTask"]] = relationship(
        "ScheduleTask",
        back_populates="schedule",
        cascade="all, delete-orphan",
        order_by="ScheduleTask.sequence_order",
    )

    __table_args__ = (
        UniqueConstraint("project_id", name="uq_project_schedules_project_id"),
    )

    def __repr__(self) -> str:
        return f"<ProjectSchedule project_id={self.project_id} start={self.schedule_start_date}>"


class ScheduleTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One stage/task within a project's schedule.

    stage_id matches a node id in knowledge/dependency_graph.json (e.g.
    "foundation"). Not a FK — dependency_graph.json is a static knowledge
    file, not a database table (ADR-006: knowledge base stays in JSON, not
    a database), so there is nothing in this schema to reference.

    No SoftDeleteMixin: a schedule's task list is fixed at creation time
    from dependency_graph.json's node set (Deliverable 1) — tasks aren't
    independently added/removed by users in Sprint 11's scope.
    """

    __tablename__ = "schedule_tasks"

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_schedules.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Matches a node id in knowledge/dependency_graph.json, e.g. "
            "'foundation', 'framing'. Not a FK — see module docstring.",
    )
    stage_label: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Human-readable label, copied from dependency_graph.json's "
            "node.label at schedule-creation time so this table reads "
            "standalone without re-parsing the knowledge file.",
    )
    sequence_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Copied from dependency_graph.json's node.sequence_order — "
            "the default display/CPM-traversal order for this project.",
    )
    planned_start_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    planned_end_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    planned_duration_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="planned_end_date - planned_start_date, stored explicitly so "
            "the CPM pass (Deliverable 5) and delay propagation "
            "(Deliverable 6) don't need to recompute it from dates.",
    )
    actual_start_date: Mapped[Optional[date_type]] = mapped_column(
        Date,
        nullable=True,
        doc="Populated by Deliverable 4 when an approved DailyLog first "
            "names this stage in current_stage/active_stages. NULL means "
            "not yet started per any approved log.",
    )
    actual_end_date: Mapped[Optional[date_type]] = mapped_column(
        Date,
        nullable=True,
        doc="Populated by Deliverable 4 once an approved DailyLog reports "
            "this stage at 100% completion or it drops out of "
            "active_stages on a later approved log.",
    )
    is_on_critical_path: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Result of this project's own CPM forward/backward pass "
            "(Deliverable 5) over planned dates — NOT copied verbatim from "
            "dependency_graph.json's generic critical path, which reflects "
            "'typical' durations that this project's planned durations may "
            "differ from.",
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    schedule: Mapped["ProjectSchedule"] = relationship(
        "ProjectSchedule", back_populates="tasks"
    )

    __table_args__ = (
        Index("ix_schedule_tasks_schedule_id", "schedule_id"),
        Index("ix_schedule_tasks_stage_id", "stage_id"),
        UniqueConstraint(
            "schedule_id", "stage_id", name="uq_schedule_tasks_schedule_stage"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ScheduleTask stage_id={self.stage_id!r} "
            f"planned={self.planned_start_date}..{self.planned_end_date} "
            f"critical={self.is_on_critical_path}>"
        )
