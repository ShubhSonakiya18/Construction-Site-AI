"""safety_talk.py — SafetyTalkService: generates the daily crew safety toolbox talk."""
from __future__ import annotations

from generation.models.outputs import ServiceType
from generation.services.base_service import BaseAIService


class SafetyTalkService(BaseAIService):
    """Generates a OSHA-referenced safety toolbox talk for the morning crew briefing."""

    @property
    def service_type(self) -> ServiceType:
        return ServiceType.SAFETY_TALK

    @property
    def prompt_name(self) -> str:
        return "safety_talk"

    def _build_user_message(self, log: dict) -> str:
        workforce = log.get("workforce") or {}
        safety = log.get("safety") or {}
        materials = log.get("materials") or {}
        weather = log.get("weather") or {}
        work = log.get("work_completed") or {}
        stage = log.get("current_stage", "Unknown")

        lines = [
            "CONSTRUCTION LOG DATA:",
            f"Date: {log.get('log_date') or 'Unknown'}",
            f"Stage: {stage}",
            "",
            "WORKFORCE ON SITE:",
            self._fmt_dict(workforce),
            "",
            "WORK COMPLETED TODAY (context for tomorrow's hazards):",
            self._fmt_dict(work),
            "",
            "MATERIALS IN USE / ON SITE:",
            self._fmt_dict(materials),
            "",
            "WEATHER CONDITIONS:",
            self._fmt_dict(weather),
            "",
            "SAFETY OBSERVATIONS AND INCIDENTS:",
            self._fmt_dict(safety),
        ]
        return "\n".join(lines)
