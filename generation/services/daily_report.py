"""daily_report.py — DailyReportService: generates the formal contractor daily report."""
from __future__ import annotations

from generation.models.outputs import ServiceType
from generation.services.base_service import BaseAIService


class DailyReportService(BaseAIService):
    """Generates a formal Markdown daily site report for contractor records."""

    @property
    def service_type(self) -> ServiceType:
        return ServiceType.DAILY_REPORT

    @property
    def prompt_name(self) -> str:
        return "daily_report"

    def _build_user_message(self, log: dict) -> str:
        project = log.get("project") or {}
        workforce = log.get("workforce") or {}
        work = log.get("work_completed") or {}
        weather = log.get("weather") or {}
        delays = log.get("delays") or {}
        safety = log.get("safety") or {}
        tomorrow = log.get("tomorrow_plan") or {}

        lines = [
            "CONSTRUCTION LOG DATA:",
            f"Date: {log.get('log_date') or 'Unknown'}",
            f"Stage: {log.get('current_stage', 'Unknown')}",
            "",
            "PROJECT:",
            self._fmt_dict(project),
            "",
            "WORKFORCE:",
            self._fmt_dict(workforce),
            "",
            "WORK COMPLETED:",
            self._fmt_dict(work),
            "",
            "WEATHER:",
            self._fmt_dict(weather),
            "",
            "DELAYS AND ISSUES:",
            self._fmt_dict(delays),
            "",
            "SAFETY:",
            self._fmt_dict(safety),
            "",
            "TOMORROW'S PLAN:",
            self._fmt_dict(tomorrow),
        ]
        return "\n".join(lines)
