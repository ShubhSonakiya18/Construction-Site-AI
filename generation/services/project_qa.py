"""project_qa.py — ProjectQAService: answers a question grounded in a project's recent logs.

Deviates from the other 4 services in one way: they take a single
ConstructionDailyLog dict, this takes {"question": str, "logs": list[dict]}.
The BaseAIService.generate(log: dict) signature is unchanged — the dict
passed in just carries a different shape. Grounding (answer only from the
supplied logs) is enforced by the prompt, not by code.
"""
from __future__ import annotations

from generation.models.outputs import ServiceType
from generation.services.base_service import BaseAIService


class ProjectQAService(BaseAIService):
    """Answers a natural-language question using only the supplied project logs."""

    @property
    def service_type(self) -> ServiceType:
        return ServiceType.PROJECT_QA

    @property
    def prompt_name(self) -> str:
        return "project_qa"

    def _build_user_message(self, log: dict) -> str:
        question = (log.get("question") or "").strip()
        logs = log.get("logs") or []

        lines = ["QUESTION:", question or "(no question provided)", "", "CONTEXT:"]
        if not logs:
            lines.append("  (no approved daily logs available for this project)")
        else:
            for entry in logs:
                lines.append(f"--- Log for {entry.get('log_date') or 'unknown date'} ---")
                lines.append(self._fmt_dict(entry))
                lines.append("")
        return "\n".join(lines)
