"""app/api/v1/projects.py — GET /projects/{id}/daily-logs.

Sprint 7 MVP scope: listing only (per docs/NEXT_SPRINT.md §2). Full
project CRUD is not in the Sprint 7 endpoint table and is deferred.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_db, require_permission
from app.core.permissions import Permission
from app.schemas.daily_log import DailyLogSummary
from app.schemas.envelope import APIResponse, PaginationMeta, success_response
from database.repositories.daily_log import DailyLogRepository

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get(
    "/{project_id}/daily-logs",
    response_model=APIResponse[list[DailyLogSummary]],
    summary="List daily logs for a project",
)
def list_project_daily_logs(
    project_id: uuid.UUID,
    status: Optional[str] = Query(
        default=None, description="Filter by review_status: draft | under_review | approved | rejected"
    ),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.PROJECT_READ)),
) -> APIResponse[list[DailyLogSummary]]:
    repo = DailyLogRepository(session)
    logs = repo.list_by_project(project_id, status=status, limit=limit, offset=offset)
    return success_response(
        [DailyLogSummary.model_validate(log) for log in logs],
        message=f"Found {len(logs)} log(s).",
        metadata=PaginationMeta(
            total=len(logs), limit=limit, offset=offset, count=len(logs)
        ).model_dump(),
    )
