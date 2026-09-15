"""
database/repositories/schedule.py — ProjectSchedule / ScheduleTask repository.

Sprint 11. Tenant scoping matches DailyLogRepository's pattern exactly:
ProjectSchedule has no direct company_id column — company is reached via
project_id -> Project.company_id, so every scoped method joins through
Project the same way get_with_children_scoped() does.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.services.schedule_service import (
    build_task_plans_from_dependency_graph,
    compute_critical_path,
)
from database.models.project import Project
from database.models.schedule import ProjectSchedule, ScheduleTask
from database.repositories.tenant import TenantContext, TenantScopedRepository


class ScheduleRepository(TenantScopedRepository[ProjectSchedule]):
    """Repository for ProjectSchedule and its ScheduleTask children."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ProjectSchedule)

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_for_project_scoped(
        self, project_id: UUID, *, tenant: TenantContext
    ) -> Optional[ProjectSchedule]:
        """Tenant-safe read of a project's schedule + all tasks. Returns
        None for both "no schedule exists yet" and "project belongs to a
        different company" — same indistinguishable-404 pattern every
        other *_scoped() method in this codebase uses."""
        stmt = (
            select(ProjectSchedule)
            .join(Project, ProjectSchedule.project_id == Project.id)
            .where(ProjectSchedule.project_id == project_id)
            .where(Project.company_id == tenant.company_id)
            .options(selectinload(ProjectSchedule.tasks))
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_task_scoped(
        self, project_id: UUID, task_id: UUID, *, tenant: TenantContext
    ) -> Optional[ScheduleTask]:
        """Tenant-safe read of a single task, scoped through its parent
        schedule's project. Used by the actual-date-population hook
        (Deliverable 4) when it needs to update one task by stage_id."""
        stmt = (
            select(ScheduleTask)
            .join(ProjectSchedule, ScheduleTask.schedule_id == ProjectSchedule.id)
            .join(Project, ProjectSchedule.project_id == Project.id)
            .where(ScheduleTask.id == task_id)
            .where(ProjectSchedule.project_id == project_id)
            .where(Project.company_id == tenant.company_id)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_task_by_stage_scoped(
        self, project_id: UUID, stage_id: str, *, tenant: TenantContext
    ) -> Optional[ScheduleTask]:
        """Same as get_task_scoped() but looked up by stage_id (e.g.
        "framing") rather than the task row's own UUID — this is what
        Deliverable 4's approval hook uses, since a DailyLog names a
        construction stage, not a schedule_tasks.id."""
        stmt = (
            select(ScheduleTask)
            .join(ProjectSchedule, ScheduleTask.schedule_id == ProjectSchedule.id)
            .join(Project, ProjectSchedule.project_id == Project.id)
            .where(ScheduleTask.stage_id == stage_id)
            .where(ProjectSchedule.project_id == project_id)
            .where(Project.company_id == tenant.company_id)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    # ── Create ────────────────────────────────────────────────────────────────

    def build_schedule_for_project(
        self, project_id: UUID, *, start_date: date, tenant: TenantContext
    ) -> Optional[ProjectSchedule]:
        """Deliverable 1 + 2 + 5: create the one-per-project schedule,
        seeded from knowledge/dependency_graph.json's generic task list,
        with planned dates and per-project critical-path membership
        computed by a real CPM pass (app/services/schedule_service.py) —
        not copied verbatim from the knowledge file's own generic
        critical path, which reflects typical durations only.

        Returns None if the project doesn't belong to this tenant (same
        404-not-403 pattern as every other tenant-scoped write) or if a
        schedule already exists for it (Sprint 11 scope: one schedule per
        project — see database/models/schedule.py). Raises whatever
        app/services/schedule_service.py raises if the knowledge base
        can't be loaded (a genuine startup/config problem, not a normal
        "not found" case, so it's not swallowed into a None return).
        """
        stmt = select(Project).where(
            Project.id == project_id, Project.company_id == tenant.company_id
        )
        project = self._session.execute(stmt).scalar_one_or_none()
        if project is None:
            return None

        existing = self.get_for_project_scoped(project_id, tenant=tenant)
        if existing is not None:
            return existing

        plans = build_task_plans_from_dependency_graph()
        computed = compute_critical_path(plans)

        schedule = ProjectSchedule(
            project_id=project_id,
            schedule_start_date=start_date,
            created_by_id=tenant.user_id,
        )
        self._session.add(schedule)
        self._session.flush()  # assigns schedule.id for the FK below

        for c in computed:
            self._session.add(
                ScheduleTask(
                    schedule_id=schedule.id,
                    stage_id=c.stage_id,
                    stage_label=c.label,
                    sequence_order=c.sequence_order,
                    planned_start_date=start_date + timedelta(days=c.planned_start_offset_days),
                    planned_end_date=start_date + timedelta(days=c.planned_end_offset_days),
                    planned_duration_days=c.duration_days,
                    is_on_critical_path=c.is_on_critical_path,
                )
            )

        # The project's total span is the latest planned_end_offset_days
        # across every task, NOT a sum of critical-path durations --
        # summing durations alone would undercount whenever a critical-
        # path edge carries a lag (e.g. the 7-day concrete-cure lag
        # between foundation and framing in dependency_graph.json), since
        # that lag adds to the span without being any task's duration.
        critical_days = max((c.planned_end_offset_days for c in computed), default=0)
        schedule.critical_path_total_days = critical_days
        schedule.projected_completion_date = start_date + timedelta(days=critical_days)

        self._session.flush()
        self._session.refresh(schedule)
        return schedule

    # ── Update (Deliverable 4) ───────────────────────────────────────────────

    def record_actual_progress(
        self,
        project_id: UUID,
        *,
        stage_id: str,
        log_date: date,
        stage_completion_percent: Optional[float],
        tenant: TenantContext,
    ) -> Optional[ScheduleTask]:
        """Called from the /daily-logs/{id}/approve flow (Deliverable 4,
        synchronous per this sprint's design decision — the update here
        is a handful of row reads/writes, not worth Celery's async
        overhead the way the multi-minute audio pipeline is).

        Sets actual_start_date to the earliest approved log_date seen for
        this stage, and actual_end_date once stage_completion_percent
        reaches 100. Both are idempotent across repeated approvals of
        logs for the same stage: actual_start_date only ever moves
        earlier, actual_end_date is only ever set once (first log to
        report 100%) and never overwritten by a later log.

        Returns None if no schedule exists for the project yet, or no
        task matches stage_id — an approval should never fail because of
        this (see app/api/v1/daily_logs.py's call site: this is a
        best-effort enrichment of the schedule, not a precondition of
        approval succeeding).
        """
        task = self.get_task_by_stage_scoped(project_id, stage_id, tenant=tenant)
        if task is None:
            return None

        if task.actual_start_date is None or log_date < task.actual_start_date:
            task.actual_start_date = log_date

        if (
            stage_completion_percent is not None
            and stage_completion_percent >= 100
            and task.actual_end_date is None
        ):
            task.actual_end_date = log_date

        self._session.flush()
        return task
