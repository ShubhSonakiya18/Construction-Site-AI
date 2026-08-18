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
