"""app/api/v1/projects.py — GET /projects/{id}/daily-logs.

Sprint 7 MVP scope: listing only (per docs/NEXT_SPRINT.md §2). Full
project CRUD is not in the Sprint 7 endpoint table and is deferred.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_app_settings, get_db, require_permission
from app.core.config import Settings
from app.core.permissions import Permission
from app.core.rate_limit import (
    RateLimiter,
    enforce_ai_generation_rate_limit,
    get_rate_limiter,
)
from app.schemas.daily_log import DailyLogSummary
from app.schemas.envelope import APIResponse, PaginationMeta, success_response
from app.schemas.project import (
    AskProjectQuestionRequest,
    AskProjectQuestionResponseData,
    CompletionTrendPoint,
    CreateScheduleRequest,
    DelayFrequencyEntry,
    ProjectAnalyticsResponseData,
    ProjectRead,
    ProjectScheduleResponseData,
    ScheduleTaskRead,
    ScheduleVarianceEntryRead,
)
from database.models.daily_log import DailyLog
from database.repositories.daily_log import DailyLogRepository
from database.repositories.project import ProjectRepository
from database.repositories.schedule import ScheduleRepository
from database.repositories.tenant import TenantContext

router = APIRouter(prefix="/projects", tags=["Projects"])

# How many recent approved logs are stuffed into the Q&A grounding context.
# Kept small deliberately: the whole context goes into one prompt, and this
# project has no vector store to fall back on if it overflows.
_QA_CONTEXT_LOG_LIMIT = 10


def _build_qa_context(logs: list[DailyLog]) -> list[dict]:
    """Flatten DailyLog rows into the plain dicts ProjectQAService formats
    into the LLM prompt. Only fields useful for answering questions are
    included — a full row dump would waste context window on IDs and
    audit columns the model cannot use."""
    context = []
    for log in logs:
        context.append({
            "log_date": log.log_date.isoformat(),
            "current_stage": log.current_stage,
            "overall_project_completion_percent": log.overall_project_completion_percent,
            "weather": log.weather,
            "total_workers_present": log.total_workers_present,
            "trades_on_site": [
                {"trade": t.trade, "workers_count": t.workers_count}
                for t in log.trades_on_site
            ],
            "work_completed": [
                {"task": w.task_description, "trade": w.trade,
                 "quantity": w.quantity_completed, "unit": w.unit_of_measure}
                for w in log.work_items
            ],
            "materials_used": [
                {"material": m.material_name, "quantity": float(m.quantity_used),
                 "unit": m.unit}
                for m in log.materials_used
            ],
            "materials_delivered": [
                {"material": m.material_name,
                 "quantity": float(m.quantity_delivered), "unit": m.unit}
                for m in log.materials_delivered
            ],
            "delays": [
                {"type": d.delay_type, "description": d.description,
                 "hours_lost": d.hours_lost, "resolved": d.delay_resolved}
                for d in log.delays
            ],
            "safety_incidents": [
                {"type": i.incident_type, "description": i.description}
                for i in log.safety_incidents
            ],
            "inspections": [
                {"type": i.inspection_type, "result": i.result}
                for i in log.inspections
            ],
            "safety_notes": log.safety_notes,
            "tomorrow_plan": log.tomorrow_plan,
        })
    return context


@router.get(
    "",
    response_model=APIResponse[list[ProjectRead]],
    summary="List projects for the caller's company",
    description=(
        "Sprint 10: closes the gap the Sprint 9 frontend carried forward — "
        "there was previously no way to discover a company's projects, so "
        "the Dashboard required a project id typed in manually. "
        "Tenant-scoped: only returns projects belonging to the caller's "
        "own company, never another tenant's."
    ),
)
def list_projects(
    status_filter: Optional[str] = Query(
        default=None, alias="status",
        description="Filter by project status, e.g. 'active'.",
    ),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.PROJECT_READ)),
) -> APIResponse[list[ProjectRead]]:
    # ProjectRepository.list_by_company() takes a raw company_id, not a
    # TenantContext — unlike get_by_id_scoped()/list_by_project_scoped(),
    # which take tenant= and scope internally, this method trusts its
    # caller to pass the right id. TenantContext.from_current_user(user)
    # is what makes that id the CALLER's own company, not an arbitrary one
    # — there is no company_id in the query string a client could tamper
    # with to see another tenant's projects.
    tenant = TenantContext.from_current_user(user)
    repo = ProjectRepository(session)
    projects = repo.list_by_company(
        tenant.company_id, status=status_filter, limit=limit, offset=offset
    )
    return success_response(
        [ProjectRead.model_validate(p) for p in projects],
        message=f"Found {len(projects)} project(s).",
        metadata=PaginationMeta(
            total=len(projects), limit=limit, offset=offset, count=len(projects)
        ).model_dump(),
    )


@router.get(
    "/{project_id}/daily-logs",
    response_model=APIResponse[list[DailyLogSummary]],
    summary="List daily logs for a project",
)
def list_project_daily_logs(
    project_id: uuid.UUID,
    status_filter: Optional[str] = Query(
        default=None, alias="status",
        description="Filter by review_status: draft | under_review | approved | rejected",
    ),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.PROJECT_READ)),
) -> APIResponse[list[DailyLogSummary]]:
    tenant = TenantContext.from_current_user(user)

    # Confirm the project itself exists and belongs to this tenant BEFORE
    # listing — otherwise a nonexistent or cross-tenant project_id would
    # silently return an empty list (200, 0 logs) instead of 404, which
    # leaks nothing but is a confusing, inconsistent contract compared to
    # every other *_or_404 lookup in this API.
    project_repo = ProjectRepository(session)
    if project_repo.get_by_id_scoped(project_id, tenant=tenant) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
        )

    repo = DailyLogRepository(session)
    logs = repo.list_by_project_scoped(
        project_id, tenant=tenant, status=status_filter, limit=limit, offset=offset
    )
    return success_response(
        [DailyLogSummary.model_validate(log) for log in logs],
        message=f"Found {len(logs)} log(s).",
        metadata=PaginationMeta(
            total=len(logs), limit=limit, offset=offset, count=len(logs)
        ).model_dump(),
    )


@router.post(
    "/{project_id}/ask",
    response_model=APIResponse[AskProjectQuestionResponseData],
    summary="Ask a question answered from this project's recent daily logs",
    description=(
        "The answer is grounded: the model is given only this project's "
        "recent approved daily logs as context and is instructed to say so "
        "when they do not cover the question, rather than answering from "
        "general knowledge. Runs synchronously, like /daily-logs/{id}/generate."
    ),
)
def ask_project_question(
    project_id: uuid.UUID,
    body: AskProjectQuestionRequest,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.PROJECT_READ)),
    settings: Settings = Depends(get_app_settings),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> APIResponse[AskProjectQuestionResponseData]:
    from generation.config import GenerationConfig
    from generation.manager import AIServiceManager
    from generation.models.outputs import ServiceType

    enforce_ai_generation_rate_limit(
        rate_limiter, user_id=user.user_id, settings=settings
    )

    tenant = TenantContext.from_current_user(user)

    project_repo = ProjectRepository(session)
    if project_repo.get_by_id_scoped(project_id, tenant=tenant) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
        )

    repo = DailyLogRepository(session)
    logs = repo.list_recent_with_children_scoped(
        project_id, tenant=tenant, limit=_QA_CONTEXT_LOG_LIMIT
    )

    manager = AIServiceManager(config=GenerationConfig.from_env())
    output = manager.generate(
        ServiceType.PROJECT_QA,
        {"question": body.question, "logs": _build_qa_context(logs)},
    )

    if not output.success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not generate an answer: {'; '.join(output.errors)}",
        )

    return success_response(
        AskProjectQuestionResponseData(
            answer=output.content,
            logs_used=len(logs),
            model=output.metadata.model if output.metadata else None,
        ),
        message="Answer generated.",
    )


@router.get(
    "/{project_id}/analytics",
    response_model=APIResponse[ProjectAnalyticsResponseData],
    summary="Basic completion trend and delay frequency for a project",
    description=(
        "Sprint 10, Deliverable 6. Both series come from the project's "
        "approved logs only, the same trust boundary the grounded Q&A "
        "service (ADR-042) applies — an unreviewed log's self-reported "
        "completion percent has not been confirmed accurate."
    ),
)
def get_project_analytics(
    project_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.PROJECT_READ)),
) -> APIResponse[ProjectAnalyticsResponseData]:
    tenant = TenantContext.from_current_user(user)

    project_repo = ProjectRepository(session)
    if project_repo.get_by_id_scoped(project_id, tenant=tenant) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
        )

    log_repo = DailyLogRepository(session)
    trend = log_repo.get_completion_trend_scoped(project_id, tenant=tenant)
    delays = log_repo.get_delay_frequency_scoped(project_id, tenant=tenant)

    return success_response(
        ProjectAnalyticsResponseData(
            completion_trend=[
                CompletionTrendPoint(log_date=d, overall_project_completion_percent=p)
                for d, p in trend
            ],
            delay_frequency=[
                DelayFrequencyEntry(
                    delay_type=t, occurrence_count=c, total_hours_lost=h,
                )
                for t, c, h in delays
            ],
            logs_analyzed=len(trend),
        ),
        message="Analytics computed.",
    )


@router.post(
    "/{project_id}/schedule",
    response_model=APIResponse[ProjectScheduleResponseData],
    status_code=status.HTTP_201_CREATED,
    summary="Create this project's schedule (Sprint 11, Deliverable 1)",
    description=(
        "Seeds a schedule from knowledge/dependency_graph.json's 23-node "
        "generic task list, with planned dates and per-project critical-"
        "path membership computed by a real CPM pass (see ADR-049 for why "
        "this can differ from the knowledge file's own generic critical "
        "path). One schedule per project — calling this again for a "
        "project that already has one returns the existing schedule "
        "unchanged rather than erroring."
    ),
)
def create_project_schedule(
    project_id: uuid.UUID,
    body: CreateScheduleRequest,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.PROJECT_MANAGE)),
) -> APIResponse[ProjectScheduleResponseData]:
    tenant = TenantContext.from_current_user(user)

    project_repo = ProjectRepository(session)
    project = project_repo.get_by_id_scoped(project_id, tenant=tenant)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
        )

    start_date = body.start_date or project.project_start_date
    if start_date is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No start_date provided and this project has no "
                "project_start_date set — provide one explicitly."
            ),
        )

    schedule_repo = ScheduleRepository(session)
    schedule = schedule_repo.build_schedule_for_project(
        project_id, start_date=start_date, tenant=tenant
    )
    session.commit()
    session.refresh(schedule)

    return success_response(
        _to_schedule_response(schedule, session=session, tenant=tenant),
        message="Schedule created.",
    )


@router.get(
    "/{project_id}/schedule",
    response_model=APIResponse[ProjectScheduleResponseData],
    summary="Get this project's schedule, tasks, and variance (Sprint 11)",
    description=(
        "Gantt-ready: each task carries planned + actual dates and "
        "critical-path membership. Also includes per-task variance "
        "(Deliverable 3) computed as of today — pure date arithmetic, no "
        "AI call (ADR-048)."
    ),
)
def get_project_schedule(
    project_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.PROJECT_READ)),
) -> APIResponse[ProjectScheduleResponseData]:
    tenant = TenantContext.from_current_user(user)

    project_repo = ProjectRepository(session)
    if project_repo.get_by_id_scoped(project_id, tenant=tenant) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
        )

    schedule_repo = ScheduleRepository(session)
    schedule = schedule_repo.get_for_project_scoped(project_id, tenant=tenant)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No schedule exists for this project yet.",
        )

    return success_response(
        _to_schedule_response(schedule, session=session, tenant=tenant, as_of=date.today()),
        message="Schedule retrieved.",
    )


def _to_schedule_response(
    schedule, *, session: Session, tenant: TenantContext, as_of: Optional[date] = None
) -> ProjectScheduleResponseData:
    """Shared response builder for the create and get endpoints above —
    both return the identical shape, so a client that creates a schedule
    gets back exactly what a subsequent GET would return, no round-trip
    needed to see the freshly-computed dates."""
    from app.services.schedule_service import compute_variance, propagate_delay_impact

    tasks_sorted = sorted(schedule.tasks, key=lambda t: t.sequence_order)
    variance = compute_variance(tasks_sorted, as_of=as_of or date.today())
    variance_by_stage = {v.stage_id: v for v in variance}

    # Sprint 11, Deliverable 6: fold every approved log's critical-path-
    # impacting delay forward, one at a time, into a running adjusted
    # date per task -- multiple independent delays compound rather than
    # overwrite each other, since each represents a real event that
    # happened. See database/repositories/daily_log.py's
    # get_critical_path_delays_scoped() for what counts as such a delay.
    log_repo = DailyLogRepository(session)
    critical_delays = log_repo.get_critical_path_delays_scoped(
        schedule.project_id, tenant=tenant
    )
    delay_adjusted_end = schedule.projected_completion_date
    if critical_delays:
        from app.services.schedule_service import _load_dependency_graph

        _, edges = _load_dependency_graph()
        # Plain, session-free copies -- propagate_delay_impact() must
        # never mutate the real ORM rows tasks_sorted holds (those stay
        # exactly as computed at schedule-creation time; this whole
        # block is a read-time-only projection, per ADR-048/this
        # function's own docstring). A tiny local class stands in for
        # ScheduleTaskLike without pulling in dataclasses.replace()
        # machinery for four fields.
        class _MutableTask:
            def __init__(self, stage_id, planned_end_date):
                self.stage_id = stage_id
                self.planned_end_date = planned_end_date

        working_tasks = [_MutableTask(t.stage_id, t.planned_end_date) for t in tasks_sorted]
        for origin_stage_id, days_lost in critical_delays:
            shift, new_end = propagate_delay_impact(
                working_tasks, edges,
                delayed_stage_id=origin_stage_id, days_lost=days_lost,
            )
            if new_end is not None:
                delay_adjusted_end = new_end
                # Apply this delay's shift before folding in the next
                # one, so two delays on a shared downstream chain
                # compound instead of each computing from the original
                # unshifted dates.
                for t in working_tasks:
                    if t.stage_id in shift:
                        t.planned_end_date = t.planned_end_date + timedelta(days=shift[t.stage_id])

    delay_impact_days = (
        (delay_adjusted_end - schedule.projected_completion_date).days
        if delay_adjusted_end and schedule.projected_completion_date
        else 0
    )

    return ProjectScheduleResponseData(
        schedule_id=schedule.id,
        project_id=schedule.project_id,
        schedule_start_date=schedule.schedule_start_date,
        critical_path_total_days=schedule.critical_path_total_days,
        projected_completion_date=schedule.projected_completion_date,
        tasks=[ScheduleTaskRead.model_validate(t) for t in tasks_sorted],
        variance=[
            ScheduleVarianceEntryRead(
                stage_id=v.stage_id, label=v.label, status=v.status,
                days_behind=v.days_behind, message=v.message,
            )
            for v in (variance_by_stage[t.stage_id] for t in tasks_sorted)
        ],
        delay_adjusted_completion_date=delay_adjusted_end,
        delay_impact_days=max(delay_impact_days, 0),
    )
