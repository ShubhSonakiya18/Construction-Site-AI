"""app/api/v1/projects.py — GET /projects/{id}/daily-logs.

Sprint 7 MVP scope: listing only (per docs/NEXT_SPRINT.md §2). Full
project CRUD is not in the Sprint 7 endpoint table and is deferred.
"""
from __future__ import annotations

import uuid
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
)
from database.models.daily_log import DailyLog
from database.repositories.daily_log import DailyLogRepository
from database.repositories.project import ProjectRepository
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
