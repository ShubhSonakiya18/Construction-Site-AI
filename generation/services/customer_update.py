"""customer_update.py — CustomerUpdateService: generates the client-facing progress email."""
from __future__ import annotations

from generation.models.outputs import ServiceType
from generation.services.base_service import BaseAIService


class CustomerUpdateService(BaseAIService):
    """Generates a friendly, jargon-free client progress email.

    Intentionally omits: worker names, safety incidents, internal delays,
    cost details — client-facing only.
    """

    @property
    def service_type(self) -> ServiceType:
        return ServiceType.CUSTOMER_UPDATE

    @property
    def prompt_name(self) -> str:
        return "customer_update"

    def _build_user_message(self, log: dict) -> str:
        project = log.get("project") or {}
        work = log.get("work_completed") or {}
        tomorrow = log.get("tomorrows_plan") or {}
        # Current stage description (no internal jargon context needed here —
        # the LLM will translate it into plain language)
        stage = log.get("current_stage", "Unknown")

        lines = [
            "CONSTRUCTION LOG DATA (client-facing context only):",
            f"Date: {log.get('log_date', 'Unknown')}",
            f"Project: {project.get('project_name', 'Your Project')}",
            f"Location: {project.get('location', '')}",
            f"Stage: {stage}",
            "",
            "WORK COMPLETED TODAY:",
            self._fmt_dict(work),
            "",
            "TOMORROW'S PLAN:",
            self._fmt_dict(tomorrow),
        ]
        return "\n".join(lines)
