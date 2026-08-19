"""app/schemas/project.py — Request/response models for the projects resource."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AskProjectQuestionRequest(BaseModel):
    """Body for POST /projects/{id}/ask."""

    question: str = Field(min_length=3, max_length=500)


class AskProjectQuestionResponseData(BaseModel):
    """Answer plus the provenance of the grounding context it was drawn
    from, so a caller can tell an "I don't know" caused by an empty
    context apart from one caused by the logs genuinely not covering it."""

    answer: str
    logs_used: int
    model: Optional[str] = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    name: str
    project_type: Optional[str] = None
    status: str
    client_name: Optional[str] = None
    project_start_date: Optional[date] = None
    planned_completion_date: Optional[date] = None
    contract_value_usd: Optional[float] = None
    created_at: datetime


class CompletionTrendPoint(BaseModel):
    """One point on the completion-over-time chart — a single approved
    log's self-reported project-wide completion percent on its date."""

    log_date: date
    overall_project_completion_percent: Optional[float] = None


class DelayFrequencyEntry(BaseModel):
    """Aggregated delay stats for one delay_type across a project's
    approved logs — see LogDelay.delay_type's doc comment
    (database/models/log_items.py) for the full fixed category list."""

    delay_type: str
    occurrence_count: int
    total_hours_lost: float


class ProjectAnalyticsResponseData(BaseModel):
    """Response for GET /projects/{id}/analytics — Sprint 10 Deliverable
    6. Both series are computed from approved logs only (same trust
    boundary the grounded Q&A service applies) and cover at most the
    project's most recent 90 approved logs for the completion trend."""

    completion_trend: list[CompletionTrendPoint]
    delay_frequency: list[DelayFrequencyEntry]
    logs_analyzed: int
