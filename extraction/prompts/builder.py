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
    "safety_meeting_conducted": <true/false>,
    "safety_meeting_duration_minutes": <integer or null>,
    "safety_meeting_topics": [<string>],
    "ppe_compliance_observed": <"full_compliance"|"minor_violations_corrected"|"violations_observed"|"not_monitored" or null>,
    "ppe_required_today": [<one or more of: "hard_hat", "high_vis_vest", "safety_glasses", "face_shield", "leather_gloves", "rubber_gloves", "cut_resistant_gloves", "steel_toe_boots", "rubber_boots", "hearing_protection", "n95_respirator", "half_face_respirator", "full_face_respirator", "fall_protection_harness", "knee_pads", "arc_flash_ppe">],
    "incidents": [
      {{"incident_type": <"first_aid"|"medical_treatment"|"lost_time_injury"|"near_miss"|"property_damage"|"environmental"|"equipment_damage">, "description": <string>, "worker_involved": <string or null>, "time_of_incident": <string or null>, "body_part_affected": <string or null>, "osha_recordable": <true/false or null>, "medical_treatment_required": <true/false or null>, "incident_reported_to": <string or null>, "corrective_actions": <string or null>, "days_away_from_work_count": <integer or null, ONLY if a number of days off work was explicitly stated>, "days_of_job_transfer_or_restriction_count": <integer or null, ONLY if explicitly stated>}}
    ],
    "hazards_identified": [
      {{"hazard_type": <"fall_risk"|"struck_by"|"caught_between"|"electrical_hazard"|"chemical_hazard"|"fire_hazard"|"heat_or_cold_stress"|"noise_hazard"|"silica_dust"|"general_dust"|"trip_hazard"|"slip_hazard"|"housekeeping"|"equipment_hazard"|"other">, "location": <string or null>, "description": <string>, "severity": <"low"|"medium"|"high"|"critical">, "corrective_action": <string or null>, "corrective_action_completed": <true/false>}}
    ],
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
    "client_contacted_today": <true/false>,
    "contact_method": <"phone_call"|"email"|"text_sms"|"in_person_visit"|"video_call"|"client_portal"|"none" or null>,
    "topics_discussed": [<string>],
    "client_concerns": [
      {{"concern_description": <string>, "priority": <"low"|"medium"|"high">, "action_required": <string or null>, "resolved": <true/false>}}
    ],
    "change_orders": [
      {{"change_order_id": <string or null>, "description": <string>, "estimated_cost_impact_usd": <number or null>, "estimated_schedule_impact_days": <number or null>, "status": <"pending_approval"|"approved"|"rejected"|"under_negotiation">}}
    ],
    "communication_notes": <string or null>
  }},
  "financials": {{
    "daily_labor_cost_usd": <number or null>,
    "daily_material_cost_usd": <number or null>,
    "daily_equipment_cost_usd": <number or null>,
    "daily_subcontractor_cost_usd": <number or null>,
    "financial_notes": <string or null>
  }}
}}

Valid current_stage values:
{stages_fmt}"""
