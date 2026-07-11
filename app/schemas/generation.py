"""app/schemas/generation.py — Request/response models for AI generation outputs."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class GenerationOutputRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    daily_log_id: Optional[UUID] = None
    service_type: str
    content: str
    is_valid: bool
    is_sent: bool
    model: Optional[str] = None
    tokens_used: Optional[int] = None
    created_at: datetime


class TriggerGenerationResponseData(BaseModel):
    """Returned by POST /daily-logs/{id}/generate — summarizes what was
    generated without repeating the full content of all 4 documents."""

    daily_log_id: UUID
    outputs_generated: int
    service_types: list[str]
