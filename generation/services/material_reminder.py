"""material_reminder.py — MaterialReminderService: generates the procurement reminder."""
from __future__ import annotations

from generation.models.outputs import ServiceType
from generation.services.base_service import BaseAIService


class MaterialReminderService(BaseAIService):
    """Generates a prioritised material procurement action list from the daily log."""

    @property
    def service_type(self) -> ServiceType:
        return ServiceType.MATERIAL_REMINDER

    @property
    def prompt_name(self) -> str:
        return "material_reminder"

    def _build_user_message(self, log: dict) -> str:
        materials = log.get("materials") or {}
        work = log.get("work_completed") or {}
        tomorrow = log.get("tomorrows_plan") or {}
        stage = log.get("current_stage", "Unknown")

        lines = [
            "CONSTRUCTION LOG DATA:",
            f"Date: {log.get('log_date', 'Unknown')}",
            f"Stage: {stage}",
            "",
            "MATERIALS (stock levels, shortages, deliveries):",
            self._fmt_dict(materials),
            "",
            "WORK COMPLETED (to infer material consumption):",
            self._fmt_dict(work),
            "",
            "TOMORROW'S PLAN (to infer material needs):",
            self._fmt_dict(tomorrow),
        ]
        return "\n".join(lines)
