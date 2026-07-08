"""
outputs.py — Pydantic output models for the Sprint 5 AI Generation Service Layer.

Why Pydantic (not dataclasses):
    Sprints 2–4 use Python dataclasses because those layers produce internal
    data structures. Sprint 5 introduces *business outputs* that will become
    API response bodies in Sprint 7 (FastAPI). Pydantic's BaseModel provides
    built-in JSON serialization, schema generation, and field validation —
    all required for REST response models. Starting with Pydantic now prevents
    a full rewrite in Sprint 7.

Model hierarchy:
    ServiceOutput          — base output from any service (success/failure/content/metadata)
    ├── DailyReport        — formal contractor report
    ├── CustomerUpdate     — client-facing email
    ├── ToolboxTalk        — safety toolbox talk
    └── MaterialReminder   — procurement reminder

    GenerationResult       — aggregated result from AIServiceManager.generate_all()
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ServiceType(str, Enum):
    DAILY_REPORT = "daily_report"
    CUSTOMER_UPDATE = "customer_update"
    SAFETY_TALK = "safety_talk"
    MATERIAL_REMINDER = "material_reminder"


class ServiceMetadata(BaseModel):
    """Observability record attached to every successful service output."""

    # Unique ID for this specific generation call (correlates logs ↔ outputs)
    generation_id: str = Field(default_factory=lambda: str(uuid4()))
    service_type: ServiceType
    provider: str = "groq"
    model: str
    prompt_name: str
    prompt_version: str
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    response_time_seconds: float = 0.0
    validation_time_seconds: float = 0.0
    retry_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0  # Groq free tier = 0


class ServiceOutput(BaseModel):
    """Base output type returned by every AI service.

    success=True  → content is the full AI-generated text; errors is empty
    success=False → content may be partial or empty; errors explains why
    """

    success: bool
    service_type: ServiceType
    content: str = ""
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: Optional[ServiceMetadata] = None

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def failure(
        cls,
        service_type: ServiceType,
        errors: list[str],
        warnings: list[str] | None = None,
    ) -> "ServiceOutput":
        return cls(
            success=False,
            service_type=service_type,
            content="",
            errors=errors,
            warnings=warnings or [],
        )


class DailyReport(ServiceOutput):
    """Formal daily site report for contractor records. Format: Markdown."""
    service_type: ServiceType = ServiceType.DAILY_REPORT


class CustomerUpdate(ServiceOutput):
    """Client-facing project update email. Format: subject + email body."""
    service_type: ServiceType = ServiceType.CUSTOMER_UPDATE


class ToolboxTalk(ServiceOutput):
    """Daily safety toolbox talk for crew briefing. Format: Markdown."""
    service_type: ServiceType = ServiceType.SAFETY_TALK


class MaterialReminder(ServiceOutput):
    """Material procurement reminder. Format: Markdown priority list."""
    service_type: ServiceType = ServiceType.MATERIAL_REMINDER


class GenerationResult(BaseModel):
    """Aggregated result from AIServiceManager.generate_all().

    success=True if at least one service succeeded.
    Individual service outputs carry their own success flags.
    """

    success: bool
    log_id: str
    log_date: str
    current_stage: str
    daily_report: DailyReport
    customer_update: CustomerUpdate
    safety_talk: ToolboxTalk
    material_reminder: MaterialReminder
    errors: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def failure(
        cls,
        log_id: str,
        log_date: str,
        current_stage: str,
        errors: list[str],
    ) -> "GenerationResult":
        return cls(
            success=False,
            log_id=log_id,
            log_date=log_date,
            current_stage=current_stage,
            daily_report=DailyReport(
                success=False,
                service_type=ServiceType.DAILY_REPORT,
                errors=errors,
            ),
            customer_update=CustomerUpdate(
                success=False,
                service_type=ServiceType.CUSTOMER_UPDATE,
                errors=errors,
            ),
            safety_talk=ToolboxTalk(
                success=False,
                service_type=ServiceType.SAFETY_TALK,
                errors=errors,
            ),
            material_reminder=MaterialReminder(
                success=False,
                service_type=ServiceType.MATERIAL_REMINDER,
                errors=errors,
            ),
            errors=errors,
        )
