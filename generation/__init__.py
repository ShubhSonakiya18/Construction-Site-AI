"""
generation — Sprint 5: AI Service Layer.

Receives a validated ConstructionDailyLog dict and produces 4 typed outputs:
  DailyReport        — Formal contractor site report (Markdown)
  CustomerUpdate     — Client-facing progress email (plain text)
  ToolboxTalk        — Safety toolbox talk briefing (Markdown)
  MaterialReminder   — Procurement action list (Markdown)

Entry point:
    from generation.manager import AIServiceManager
    manager = AIServiceManager()
    result = manager.generate_all(extracted_log)
"""

from generation.config import GenerationConfig
from generation.manager import AIServiceManager
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
    "AIServiceManager",
    "GenerationConfig",
    "GenerationResult",
    "ServiceOutput",
    "ServiceMetadata",
    "ServiceType",
    "DailyReport",
    "CustomerUpdate",
    "ToolboxTalk",
    "MaterialReminder",
]
