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


class ScheduleTaskRead(BaseModel):
    """One task within GET /projects/{id}/schedule's response — Sprint 11.

    Gantt-ready: a frontend needs only planned/actual start+end and
    is_on_critical_path to draw one bar per task plus the critical-path
    highlight, with no further computation on the client.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    stage_id: str
    stage_label: str
    sequence_order: int
    planned_start_date: date
    planned_end_date: date
    planned_duration_days: int
    actual_start_date: Optional[date] = None
    actual_end_date: Optional[date] = None
    is_on_critical_path: bool


class ScheduleVarianceEntryRead(BaseModel):
    """One task's schedule variance — Sprint 11 Deliverable 3. Pure date
    arithmetic (see ADR-048), not AI-generated text."""

    stage_id: str
    label: str
    status: str
    days_behind: int
    message: str


class ProjectScheduleResponseData(BaseModel):
    """Response for GET /projects/{id}/schedule — Sprint 11 Deliverables
    1, 2, 3, and 6. Variance and delay-impact are both computed at read
    time (not persisted) — see ADR-048 and app/services/schedule_service.py
    — so this response always reflects the project's current approved
    logs, never a stale snapshot from whenever the schedule was created."""

    schedule_id: UUID
    project_id: UUID
    schedule_start_date: date
    critical_path_total_days: Optional[int] = None
    projected_completion_date: Optional[date] = None
    tasks: list[ScheduleTaskRead]
    variance: list[ScheduleVarianceEntryRead]
    delay_adjusted_completion_date: Optional[date] = Field(
        default=None,
        description=(
            "Sprint 11 Deliverable 6: projected_completion_date after "
            "propagating every approved log's critical-path-impacting "
            "delay forward through the dependency graph. Equal to "
            "projected_completion_date when no such delay has been "
            "recorded yet."
        ),
    )
    delay_impact_days: int = Field(
        default=0,
        description="Total days delay_adjusted_completion_date has moved "
                     "past projected_completion_date.",
    )


class CreateScheduleRequest(BaseModel):
    """Body for POST /projects/{id}/schedule. start_date defaults to the
    project's own project_start_date if omitted — see the router for the
    fallback logic and the 400 raised when neither is available."""

    start_date: Optional[date] = None
