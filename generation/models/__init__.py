"""generation.models — Pydantic output models for all AI generation services."""

from generation.models.outputs import (
    CustomerUpdate,
    DailyReport,
    GenerationResult,
    MaterialReminder,
    ServiceMetadata,
    ServiceOutput,
    ServiceType,
    ToolboxTalk,
)

__all__ = [
    "ServiceType",
    "ServiceMetadata",
    "ServiceOutput",
    "DailyReport",
    "CustomerUpdate",
    "ToolboxTalk",
    "MaterialReminder",
    "GenerationResult",
]
