"""app/api/v1/projects.py — GET /projects/{id}/daily-logs.

Sprint 7 MVP scope: listing only (per docs/NEXT_SPRINT.md §2). Full
project CRUD is not in the Sprint 7 endpoint table and is deferred.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_db, require_permission
from app.core.permissions import Permission
from app.schemas.daily_log import DailyLogSummary
from app.schemas.envelope import APIResponse, PaginationMeta, success_response
from database.repositories.daily_log import DailyLogRepository
from database.repositories.project import ProjectRepository
from database.repositories.tenant import TenantContext

router = APIRouter(prefix="/projects", tags=["Projects"])


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
