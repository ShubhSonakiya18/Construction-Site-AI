"""
builder.py — Builds the extraction prompt from transcript text + schema context.

Keeps all prompt logic in one place so it can be iterated without touching engine
or pipeline code. The system prompt lives in system_prompt.txt for easy editing.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


_SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.txt"


def _load_system_prompt() -> str:
    return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()


class PromptBuilder:
    """
    Builds extraction prompts from transcript text and schema-derived context.

    Constructed once per pipeline instance; build_prompt() is called per
    extraction run.
    """

    def __init__(
        self,
        stage_enum: list[str],
        weather_enum: list[str],
        trade_enum: list[str],
    ) -> None:
        self._stage_enum = stage_enum
        self._weather_enum = weather_enum
        self._trade_enum = trade_enum
        self._system_prompt = _load_system_prompt()

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def build_prompt(
        self,
        transcript_text: str,
        log_date: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> str:
        schema_ref = self._build_schema_reference()
        date_hint = f"\nLog date (use for log_date field): {log_date}" if log_date else ""
        project_hint = f"\nProject ID (use for project.project_id): {project_id}" if project_id else ""

        return f"""Extract a ConstructionDailyLog JSON from the following foreman voice transcript.{date_hint}{project_hint}

SCHEMA REFERENCE (key fields and valid enum values):
{schema_ref}

TRANSCRIPT:
{transcript_text.strip() if transcript_text else "(empty)"}

OUTPUT (valid JSON only, no explanation):"""

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_schema_reference(self) -> str:
        stages_fmt = json.dumps(self._stage_enum, indent=2)
        weather_fmt = json.dumps(self._weather_enum, indent=2)
        trades_fmt = json.dumps(self._trade_enum, indent=2)

        return f"""{{
  "log_date": "YYYY-MM-DD",
  "current_stage": <one of: {", ".join(self._stage_enum[:8])} ... {len(self._stage_enum)} total values>,
  "stage_completion_percent": <0-100 or null>,
  "overall_project_completion_percent": <0-100 or null>,
  "weather": {{
    "morning_condition": <one of: {", ".join(self._weather_enum)}>,
    "afternoon_condition": <one of: {", ".join(self._weather_enum)}>,
    "temperature_high_celsius": <number or null>,
    "temperature_low_celsius": <number or null>,
    "precipitation_mm": <number or null>,
    "work_stopped_due_to_weather": <true/false or null>,
    "weather_impact_level": <"none"|"minor"|"moderate"|"severe" or null>,
    "weather_notes": <string or null>
  }},
  "workforce": {{
    "total_workers_present": <integer or null>,
    "total_workers_scheduled": <integer or null>,
    "total_man_hours_worked": <number or null>,
    "trades_on_site": [
      {{"trade": <one of: {", ".join(self._trade_enum[:5])} ...>, "workers_count": <int>, "hours_worked": <number or null>, "notes": <string or null>}}
    ],
    "late_arrivals": [{{"worker_identifier": <string>, "trade": <string>, "minutes_late": <int>, "reason": <string or null>}}],
    "absences": [{{"worker_identifier": <string>, "trade": <string>, "reason": <string or null>}}],
    "workforce_notes": <string or null>
  }},
  "work_completed": [
    {{"task_description": <string>, "trade": <string or null>, "location_on_site": <string or null>, "quantity_completed": <number or null>, "unit_of_measure": <string or null>, "notes": <string or null>}}
  ],
  "materials": {{
    "used_today": [{{"material_name": <string>, "quantity_used": <number or null>, "unit": <string or null>}}],
    "delivered_today": [{{"material_name": <string>, "quantity_delivered": <number or null>, "unit": <string or null>, "supplier": <string or null>}}],
    "required_for_tomorrow": [{{"material_name": <string>, "quantity_needed": <number or null>, "unit": <string or null>}}],
    "shortage_flags": [<string>]
  }},
  "safety": {{
    "safety_meeting_held": <true/false or null>,
    "safety_meeting_topic": <string or null>,
    "ppe_compliance_percent": <0-100 or null>,
    "incidents": [],
    "hazards_identified": [<string>],
    "safety_notes": <string or null>
  }},
  "delays": [
    {{"delay_type": <"weather"|"material_shortage"|"equipment_failure"|"labor_shortage"|"inspection_hold"|"design_change"|"permit_issue"|"subcontractor_delay"|"rework_required"|"other">, "hours_lost": <number>, "description": <string or null>, "schedule_impact": <string or null>}}
  ],
  "tomorrows_plan": {{
    "planned_tasks": [<string>],
    "materials_to_order": [<string>],
    "subcontractors_expected": [<string>],
    "inspections_scheduled": [<string>],
    "notes": <string or null>
  }},
  "client_communication": {{
    "contact_made": <true/false or null>,
    "contact_method": <string or null>,
    "customer_concerns": <string or null>,
    "change_orders_discussed": <true/false or null>,
    "notes": <string or null>
  }}
}}

Valid current_stage values:
{stages_fmt}"""
