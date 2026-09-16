"""app/api/v1/projects.py — GET /projects/{id}/daily-logs.

Sprint 7 MVP scope: listing only (per docs/NEXT_SPRINT.md §2). Full
project CRUD is not in the Sprint 7 endpoint table and is deferred.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
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
from app.schemas.inventory import (
    CreatePurchaseOrderRequest,
    InventoryItemRead,
    LeadTimeWarningRead,
    ProjectInventoryResponseData,
    PurchaseOrderRead,
    UpdatePurchaseOrderStatusRequest,
)
from app.schemas.project import (
    AskProjectQuestionRequest,
    AskProjectQuestionResponseData,
    BudgetVarianceRead,
    ChangeOrderSummaryEntry,
    CompletionTrendPoint,
    CreateScheduleRequest,
    DailyCostPointRead,
    DelayFrequencyByTradeEntry,
    DelayFrequencyEntry,
    EarnedValueRead,
    MaterialCostEstimateLineRead,
    ProjectAnalyticsResponseData,
    ProjectCostEstimateRead,
    ProjectRead,
    ProductivityByStageTradeEntry,
    ProjectScheduleResponseData,
    SafetyIncidentBreakdownEntry,
    SafetyIncidentTrendPoint,
    SafetyProactiveWarningsRead,
    StageCostEstimateRead,
    UnresolvedHazardWarningRead,
    ScheduleTaskRead,
    ScheduleVarianceEntryRead,
)
from app.services.cost_estimation_service import compute_project_cost_estimate
from app.services.cost_service import (
    build_cost_trend,
    compute_budget_variance,
    compute_earned_value,
)
from app.services.safety_trend_service import (
    compute_days_since_last_incident,
    compute_incidence_rate,
    compute_unresolved_hazard_warnings,
)
from database.models.daily_log import DailyLog
from database.repositories.daily_log import DailyLogRepository
from database.repositories.inventory import InventoryRepository
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
    project = project_repo.get_by_id_scoped(project_id, tenant=tenant)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
        )

    log_repo = DailyLogRepository(session)
    trend = log_repo.get_completion_trend_scoped(project_id, tenant=tenant)
    delays = log_repo.get_delay_frequency_scoped(project_id, tenant=tenant)
    delays_by_trade = log_repo.get_delay_frequency_by_trade_scoped(project_id, tenant=tenant)
    safety_trend = log_repo.get_safety_incident_trend_scoped(project_id, tenant=tenant)
    safety_breakdown = log_repo.get_safety_incident_breakdown_scoped(project_id, tenant=tenant)
    productivity = log_repo.get_productivity_by_stage_and_trade_scoped(project_id, tenant=tenant)

    # Sprint 14, Deliverables 1/2/4: cost figures come from the four
    # components the extraction prompt asks for (ADR-058); daily and
    # running totals are computed here, never extracted. Budget variance
    # compares that running total against Project.contract_value_usd --
    # the only budget figure this schema records.
    cost_rows = log_repo.get_daily_cost_trend_scoped(project_id, tenant=tenant)
    cost_trend = build_cost_trend(cost_rows)
    total_spend = cost_trend[-1].cumulative_spend_to_date_usd if cost_trend else 0.0
    budget_variance = compute_budget_variance(
        contract_value_usd=(
            float(project.contract_value_usd)
            if project.contract_value_usd is not None
            else None
        ),
        total_spend_to_date_usd=total_spend,
    )
    material_cost_line_items = log_repo.get_material_cost_from_line_items_scoped(
        project_id, tenant=tenant
    )
    change_orders = log_repo.get_change_order_summary_scoped(project_id, tenant=tenant)

    # Sprint 15, Deliverable 4 (ADR-063): "proactive warning" as a
    # computed read-time field, not a pushed notification -- same
    # resolution Sprint 14's "budget variance alert" already reached,
    # since this codebase has no scheduler or notification
    # infrastructure.
    hazards_with_dates = log_repo.get_unresolved_hazards_scoped(project_id, tenant=tenant)
    most_recent_incident_date = log_repo.get_most_recent_incident_date_scoped(
        project_id, tenant=tenant
    )
    recordable_count, total_hours = log_repo.get_recordable_incident_count_and_hours_scoped(
        project_id, tenant=tenant
    )
    today = date.today()
    incidence_rate, incidence_rate_unavailable_reason = compute_incidence_rate(
        recordable_incident_count=recordable_count, total_hours_worked=total_hours,
    )
    safety_warnings = SafetyProactiveWarningsRead(
        unresolved_hazards=[
            UnresolvedHazardWarningRead(
                hazard_type=w.hazard_type, severity=w.severity,
                description=w.description, days_open=w.days_open,
            )
            for w in compute_unresolved_hazard_warnings(hazards_with_dates, as_of=today)
        ],
        days_since_last_incident=compute_days_since_last_incident(
            most_recent_incident_date, as_of=today
        ),
        incidence_rate_per_200k_hours=incidence_rate,
        incidence_rate_unavailable_reason=incidence_rate_unavailable_reason,
    )

    # Sprint 13, Deliverable 1 (ADR-052): if this project has a Sprint 11
    # schedule, surface its projected/delay-adjusted completion dates
    # alongside the log-derived trend -- the first place these two data
    # sources (Sprint 10 analytics, Sprint 11 scheduling) appear
    # together. A project with no schedule yet simply omits both, same
    # as every other optional cross-feature field in this codebase.
    schedule = ScheduleRepository(session).get_for_project_scoped(
        project_id, tenant=tenant
    )
    projected_completion_date = None
    delay_adjusted_completion_date = None
    if schedule is not None:
        projected_completion_date = schedule.projected_completion_date
        delay_adjusted_completion_date = _compute_delay_adjusted_completion(
            schedule, session=session, tenant=tenant
        )

    # Sprint 14, Deliverable 3 (ADR-060): a single as-of-today EVM
    # snapshot. EV reuses the same overall_project_completion_percent
    # completion_trend already shows, so this doesn't introduce a second,
    # possibly-disagreeing "percent done" figure. AC reuses Deliverable 2's
    # already-computed total_spend. PV needs a schedule; when there isn't
    # one, PV/SPI are null but EV/CPI can still compute from contract
    # value and completion percent alone -- see compute_earned_value()'s
    # own docstring for the per-field degradation.
    # The most recent approved log doesn't always report a completion
    # percent (it's an optional field -- see CompletionTrendPoint), so
    # walk backward for the most recent log that actually did, rather
    # than taking trend[-1] and getting None even when an earlier log
    # has a real value. Confirmed live: the seeded project's two most
    # recent logs both omit it while an earlier one reports 28%.
    latest_completion_percent = next(
        (percent for _, percent in reversed(trend) if percent is not None), None
    )
    evm_snapshot = compute_earned_value(
        contract_value_usd=(
            float(project.contract_value_usd)
            if project.contract_value_usd is not None
            else None
        ),
        overall_project_completion_percent=latest_completion_percent,
        schedule_start_date=schedule.schedule_start_date if schedule else None,
        projected_completion_date=schedule.projected_completion_date if schedule else None,
        as_of=date.today(),
        total_spend_to_date_usd=total_spend,
    )

    # Sprint 17 (ADR-065): a materials-only reference-cost range, from
    # real reference data -- never a bid or a historical-data-driven
    # prediction (this codebase has only one project, so no such history
    # exists). Reuses the project's own real ScheduleTask stage_id list
    # (Sprint 11) rather than the dependency graph's full generic stage
    # set -- a stage this project's schedule doesn't include contributes
    # nothing to the estimate. A project with no schedule yet gets a
    # clear unavailable_reason rather than an empty-stage-list estimate
    # that looks like "nothing costs anything."
    if schedule is None:
        cost_estimate = compute_project_cost_estimate(
            project_size_sqft=None, stage_ids=[],
        )
        cost_estimate.unavailable_reason = (
            "This project has no schedule yet -- a reference-cost "
            "estimate needs a stage list to know which materials apply."
        )
    else:
        cost_estimate = compute_project_cost_estimate(
            project_size_sqft=(
                float(project.project_size_sqft)
                if project.project_size_sqft is not None
                else None
            ),
            stage_ids=[task.stage_id for task in schedule.tasks],
            contract_value_usd=(
                float(project.contract_value_usd)
                if project.contract_value_usd is not None
                else None
            ),
        )

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
            delay_frequency_by_trade=[
                DelayFrequencyByTradeEntry(
                    trade=t, delay_count=c, total_hours_lost=h,
                )
                for t, c, h in delays_by_trade
            ],
            safety_incident_trend=[
                SafetyIncidentTrendPoint(
                    log_date=d, incident_count=c, osha_recordable_count=o,
                )
                for d, c, o in safety_trend
            ],
            safety_incident_breakdown=[
                SafetyIncidentBreakdownEntry(
                    incident_type=t, incident_count=c, osha_recordable_count=o,
                )
                for t, c, o in safety_breakdown
            ],
            safety_proactive_warnings=safety_warnings,
            productivity_by_stage_trade=[
                ProductivityByStageTradeEntry(
                    current_stage=s, trade=t, avg_task_completion_percent=a, work_item_count=c,
                )
                for s, t, a, c in productivity
            ],
            daily_cost_trend=[
                DailyCostPointRead(
                    log_date=p.log_date,
                    daily_labor_cost_usd=p.daily_labor_cost_usd,
                    daily_material_cost_usd=p.daily_material_cost_usd,
                    daily_equipment_cost_usd=p.daily_equipment_cost_usd,
                    daily_subcontractor_cost_usd=p.daily_subcontractor_cost_usd,
                    daily_total_cost_usd=p.daily_total_cost_usd,
                    cumulative_spend_to_date_usd=p.cumulative_spend_to_date_usd,
                )
                for p in cost_trend
            ],
            budget_variance=BudgetVarianceRead(
                contract_value_usd=budget_variance.contract_value_usd,
                total_spend_to_date_usd=budget_variance.total_spend_to_date_usd,
                budget_remaining_usd=budget_variance.budget_remaining_usd,
                percent_of_budget_spent=budget_variance.percent_of_budget_spent,
                status=budget_variance.status,
                material_cost_from_line_items_usd=material_cost_line_items,
            ),
            earned_value=EarnedValueRead(
                planned_value_usd=evm_snapshot.planned_value_usd,
                earned_value_usd=evm_snapshot.earned_value_usd,
                actual_cost_usd=evm_snapshot.actual_cost_usd,
                cost_performance_index=evm_snapshot.cost_performance_index,
                schedule_performance_index=evm_snapshot.schedule_performance_index,
            ),
            change_order_summary=[
                ChangeOrderSummaryEntry(
                    status=s, change_order_count=c, total_cost_impact_usd=t,
                )
                for s, c, t in change_orders
            ],
            cost_estimate=ProjectCostEstimateRead(
                project_size_sqft=cost_estimate.project_size_sqft,
                stages=[
                    StageCostEstimateRead(
                        stage_id=stage.stage_id,
                        materials=[
                            MaterialCostEstimateLineRead(
                                material_id=m.material_id,
                                material_name=m.material_name,
                                unit=m.unit,
                                estimated_quantity=m.estimated_quantity,
                                low_usd=m.low_usd,
                                high_usd=m.high_usd,
                            )
                            for m in stage.materials
                        ],
                        low_usd=stage.low_usd,
                        high_usd=stage.high_usd,
                    )
                    for stage in cost_estimate.stages
                ],
                low_usd=cost_estimate.low_usd,
                high_usd=cost_estimate.high_usd,
                unavailable_reason=cost_estimate.unavailable_reason,
                contract_comparison_note=cost_estimate.contract_comparison_note,
            ),
            logs_analyzed=len(trend),
            projected_completion_date=projected_completion_date,
            delay_adjusted_completion_date=delay_adjusted_completion_date,
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


def _compute_delay_adjusted_completion(
    schedule, *, session: Session, tenant: TenantContext
) -> date:
    """Sprint 11, Deliverable 6, factored out so Sprint 13's analytics
    endpoint (get_project_analytics()) can reuse the exact same
    computation _to_schedule_response() uses, rather than a second copy
    that could silently drift from it (see ADR-052 — this is why
    Deliverable 1 extends the analytics response instead of building a
    parallel one). Folds every approved log's critical-path-impacting
    delay forward, one at a time, into a running adjusted date per task
    — multiple independent delays compound rather than overwrite each
    other, since each represents a real event that happened. See
    database/repositories/daily_log.py's get_critical_path_delays_scoped()
    for what counts as such a delay.
    """
    from app.services.schedule_service import propagate_delay_impact

    tasks_sorted = sorted(schedule.tasks, key=lambda t: t.sequence_order)
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
        # function is a read-time-only projection, per ADR-048). A tiny
        # local class stands in for ScheduleTaskLike without pulling in
        # dataclasses.replace() machinery for four fields.
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

    return delay_adjusted_end


def _to_schedule_response(
    schedule, *, session: Session, tenant: TenantContext, as_of: Optional[date] = None
) -> ProjectScheduleResponseData:
    """Shared response builder for the create and get endpoints above —
    both return the identical shape, so a client that creates a schedule
    gets back exactly what a subsequent GET would return, no round-trip
    needed to see the freshly-computed dates."""
    from app.services.schedule_service import compute_variance

    tasks_sorted = sorted(schedule.tasks, key=lambda t: t.sequence_order)
    variance = compute_variance(tasks_sorted, as_of=as_of or date.today())
    variance_by_stage = {v.stage_id: v for v in variance}

    delay_adjusted_end = _compute_delay_adjusted_completion(
        schedule, session=session, tenant=tenant
    )
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


@router.get(
    "/{project_id}/inventory",
    response_model=APIResponse[ProjectInventoryResponseData],
    summary="Get this project's inventory, purchase orders, and lead-time warnings (Sprint 12)",
    description=(
        "Includes lead-time warnings (Deliverable 4) computed at read "
        "time against the project's current schedule — pure date "
        "arithmetic, no AI call (see app/services/inventory_service.py)."
    ),
)
def get_project_inventory(
    project_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.PROJECT_READ)),
) -> APIResponse[ProjectInventoryResponseData]:
    tenant = TenantContext.from_current_user(user)

    project_repo = ProjectRepository(session)
    if project_repo.get_by_id_scoped(project_id, tenant=tenant) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
        )

    items = InventoryRepository(session).list_for_project_scoped(
        project_id, tenant=tenant
    )
    warnings = _compute_lead_time_warnings(session, project_id, items, tenant=tenant)

    return success_response(
        ProjectInventoryResponseData(
            project_id=project_id,
            items=[InventoryItemRead.model_validate(i) for i in items],
            lead_time_warnings=warnings,
        ),
        message="Inventory retrieved.",
    )


@router.post(
    "/{project_id}/inventory/{item_id}/purchase-orders",
    response_model=APIResponse[PurchaseOrderRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a purchase order for an inventory item (Sprint 12, Deliverable 3)",
    description=(
        "The human-initiated counterpart to the auto-generated path "
        "(reorder-point check on log approval). Always created as "
        "status=\"draft\"."
    ),
)
def create_purchase_order(
    project_id: uuid.UUID,
    item_id: uuid.UUID,
    body: CreatePurchaseOrderRequest,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.PROJECT_MANAGE)),
) -> APIResponse[PurchaseOrderRead]:
    tenant = TenantContext.from_current_user(user)

    po = InventoryRepository(session).create_purchase_order(
        project_id, item_id,
        quantity_ordered=body.quantity_ordered,
        supplier=body.supplier,
        unit_cost_usd=body.unit_cost_usd,
        tenant=tenant,
    )
    if po is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found.",
        )
    session.commit()
    session.refresh(po)

    return success_response(
        PurchaseOrderRead.model_validate(po), message="Purchase order created."
    )


@router.patch(
    "/{project_id}/inventory/{item_id}/purchase-orders/{po_id}",
    response_model=APIResponse[PurchaseOrderRead],
    summary="Update a purchase order's status (Sprint 12)",
)
def update_purchase_order_status(
    project_id: uuid.UUID,
    item_id: uuid.UUID,
    po_id: uuid.UUID,
    body: UpdatePurchaseOrderStatusRequest,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.PROJECT_MANAGE)),
) -> APIResponse[PurchaseOrderRead]:
    tenant = TenantContext.from_current_user(user)

    po = InventoryRepository(session).update_purchase_order_status_scoped(
        project_id, item_id, po_id, status=body.status, tenant=tenant,
    )
    if po is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase order not found.",
        )
    session.commit()
    session.refresh(po)

    return success_response(
        PurchaseOrderRead.model_validate(po), message="Purchase order updated."
    )


@router.get(
    "/{project_id}/osha-300-log",
    summary="Generate an OSHA Form 300 Log PDF for a project's calendar year",
    description=(
        "Sprint 15, Deliverable 3. Renders a tabular OSHA Form 300 Log "
        "PDF for the project's recordable safety incidents in the given "
        "calendar year. An incident missing its OSHA classification or "
        "a resolved worker match is excluded from the table and counted "
        "in a review note on the document (ADR-061) -- never silently "
        "omitted with no trace. Gated on DAILY_LOG_GENERATE, not "
        "DAILY_LOG_READ or PROJECT_READ: this produces an official "
        "compliance document, not a read of existing data, and the "
        "client role (which holds DAILY_LOG_READ) should not be able "
        "to pull it. Returns raw PDF bytes with a file-download "
        "Content-Disposition header, not the standard APIResponse "
        "envelope, matching GET /daily-logs/{id}/outputs/{output_id}/pdf's "
        "existing precedent for binary responses."
    ),
    responses={200: {"content": {"application/pdf": {}}}},
)
def get_project_osha_300_log(
    project_id: uuid.UUID,
    year: int = Query(..., description="Calendar year, e.g. 2026", ge=2000, le=2100),
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.DAILY_LOG_GENERATE)),
) -> Response:
    from app.services.osha_log_export import (
        OshaLogIncident,
        build_osha_300_log,
        classify_incident_readiness,
    )

    tenant = TenantContext.from_current_user(user)
    project = ProjectRepository(session).get_by_id_scoped(project_id, tenant=tenant)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
        )

    rows = DailyLogRepository(session).get_safety_incidents_for_year_scoped(
        project_id, calendar_year=year, tenant=tenant
    )

    incidents: list[OshaLogIncident] = []
    for row in rows:
        is_ready, reason = classify_incident_readiness(
            osha_recordable=row.osha_recordable,
            osha_classification=row.osha_classification,
            worker_id=row.worker_id,
            worker_match_status=row.worker_match_status,
        )
        incidents.append(OshaLogIncident(
            case_number=row.case_number,
            log_date=row.daily_log.log_date,
            worker_name=row.worker.full_name if row.worker else row.worker_involved,
            job_title=row.worker.role if row.worker else None,
            description=row.description,
            osha_classification=row.osha_classification,
            injury_illness_type=row.injury_illness_type,
            days_away_from_work_count=row.days_away_from_work_count,
            days_of_job_transfer_or_restriction_count=row.days_of_job_transfer_or_restriction_count,
            is_review_ready=is_ready,
            review_reason=reason,
        ))

    result = build_osha_300_log(incidents, project_name=project.name, calendar_year=year)
    # A Content-Disposition header value must be latin-1-encodable (HTTP
    # headers, not the PDF body) -- a real project name can contain an
    # em-dash or other non-latin-1 character (the seeded sample project's
    # own name is "Johnson Residence — 123 Oak Street"), so this can't
    # just lowercase-and-replace-spaces the raw name the way a
    # pure-ASCII name would tempt. Slugify to ASCII-only, matching the
    # em-dash-in-a-PDF-title bug this same deliverable found and fixed
    # in build_osha_300_log()'s title= parameter.
    project_slug = re.sub(r"[^a-z0-9]+", "-", project.name.lower()).strip("-") or "project"
    filename = f"osha-300-log-{project_slug}-{year}.pdf"
    return Response(
        content=result.pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Osha-Log-Included-Count": str(result.included_count),
            "X-Osha-Log-Needs-Review-Count": str(len(result.excluded_needs_review)),
        },
    )


def _compute_lead_time_warnings(
    session: Session, project_id: uuid.UUID, items: list, *, tenant: TenantContext
) -> list[LeadTimeWarningRead]:
    """Deliverable 4: cross-reference each inventory item against the
    project's schedule tasks via applicable_stage_id. Read-only, computed
    fresh on every call — never persisted, matching how Sprint 11's
    variance/delay_adjusted_completion_date fields work."""
    from app.services.inventory_service import compute_lead_time_warning

    schedule = ScheduleRepository(session).get_for_project_scoped(
        project_id, tenant=tenant
    )
    if schedule is None:
        return []

    tasks_by_stage = {t.stage_id: t for t in schedule.tasks}
    today = date.today()

    warnings: list[LeadTimeWarningRead] = []
    for item in items:
        matching_task = (
            tasks_by_stage.get(item.applicable_stage_id)
            if item.applicable_stage_id
            else None
        )
        has_open_covering_order = any(
            po.status in ("submitted", "delivered") for po in item.purchase_orders
        )
        warning = compute_lead_time_warning(
            item, matching_task,
            has_open_covering_order=has_open_covering_order,
            as_of=today,
        )
        if warning is not None:
            warnings.append(LeadTimeWarningRead(
                material_name=warning.material_name,
                stage_id=warning.stage_id,
                status=warning.status,
                days_until_stage_start=warning.days_until_stage_start,
                order_by_date=warning.order_by_date,
                message=warning.message,
            ))
    return warnings
