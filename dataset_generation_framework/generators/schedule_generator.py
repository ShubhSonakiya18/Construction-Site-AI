"""
schedule_generator.py — Generates project schedule records with planned vs. actual dates.

Each record represents one construction project's full schedule:
- Planned start/end dates per stage (from DAG typical_duration_days)
- Actual dates with realistic variance (weather delays, rework, etc.)
- Overall delay summary: on_time | delayed | ahead_of_schedule
- Delay breakdown by category (weather, material, labor, etc.)

DESIGN: Uses topological_order() from KnowledgeBase to sequence stages correctly.
All duration data comes from dependency_graph.json — zero hardcoded durations.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Iterator

from faker import Faker

from dataset_generation_framework.config import (
    CONTRACT_VALUE_MAX_USD,
    CONTRACT_VALUE_MIN_USD,
    PROJECT_SIZE_SQFT_MAX,
    PROJECT_SIZE_SQFT_MIN,
    PROJECT_START_DATE_RANGE_DAYS,
    SCHEMA_VERSION,
    STAGE_DURATION_VARIANCE,
    VALIDATE_EVERY_N,
)
from dataset_generation_framework.core.knowledge_loader import KnowledgeBase
from dataset_generation_framework.generators.base_generator import BaseGenerator

logger = logging.getLogger(__name__)

_REFERENCE_DATE = date(2023, 1, 1)

# Delay category weights (out of 100%, sum ≤ 100%)
_DELAY_CATEGORIES = ["weather", "material_shortage", "labor_shortage",
                     "inspection_wait", "rework", "client_decision", "other"]
_DELAY_WEIGHTS    = [0.30, 0.20, 0.15, 0.15, 0.10, 0.05, 0.05]


class ScheduleGenerator(BaseGenerator):
    """Generates ConstructionProjectSchedule records."""

    def __init__(self, kb: KnowledgeBase, seed: int) -> None:
        super().__init__(kb, seed)
        self._topo_order = [
            n["id"] for n in self.kb.dag_nodes()
            if n.get("type") != "milestone"
        ]
        self._durations: dict[str, int] = {
            n["id"]: n.get("typical_duration_days", 5)
            for n in self.kb.dag_nodes()
        }

    def generate_one(self, **kwargs: Any) -> dict:
        fake = Faker("en_US")
        fake.seed_instance(self.rng.randint(0, 999999))

        start_offset = self.rng.randint(0, PROJECT_START_DATE_RANGE_DAYS)
        planned_start = _REFERENCE_DATE + timedelta(days=start_offset)

        sqft = self.rng.randint(PROJECT_SIZE_SQFT_MIN, PROJECT_SIZE_SQFT_MAX)
        contract = round(self.rng.uniform(CONTRACT_VALUE_MIN_USD, CONTRACT_VALUE_MAX_USD), -3)

        stage_schedules, planned_end, actual_end = self._build_stage_schedules(planned_start)

        total_planned_days = (planned_end - planned_start).days
        total_actual_days  = (actual_end - planned_start).days
        delay_days = max(0, total_actual_days - total_planned_days)

        if delay_days == 0 and self.rng.random() > 0.8:
            status = "ahead_of_schedule"
        elif delay_days == 0:
            status = "on_time"
        else:
            status = "delayed"

        delay_breakdown = self._build_delay_breakdown(delay_days)

        client_last = fake.last_name()
        client_first = fake.first_name()

        return {
            "schedule_id": self.seeded_uuid(),
            "schema_version": SCHEMA_VERSION,
            "project_id": self.seeded_uuid(),
            "project_name": f"{client_last} Residence — {fake.street_address()}",
            "project_type": "residential_single_family",
            "project_size_sqft": sqft,
            "client_name": f"{client_first} {client_last}",
            "contractor_company": fake.company(),
            "foreman_name": fake.name_male(),
            "permit_number": f"BP-{self.rng.randint(10000, 99999)}",
            "contract_value_usd": contract,
            "planned_start_date": planned_start.isoformat(),
            "planned_completion_date": planned_end.isoformat(),
            "actual_start_date": planned_start.isoformat(),
            "actual_completion_date": (
                actual_end.isoformat() if status == "on_time" else None
            ),
            "projected_completion_date": actual_end.isoformat(),
            "schedule_status": status,
            "total_planned_working_days": total_planned_days,
            "total_actual_working_days": total_actual_days if status != "delayed" else None,
            "total_delay_days": delay_days,
            "delay_breakdown_by_category": delay_breakdown,
            "stage_schedules": stage_schedules,
            "critical_path_stages": self.kb.critical_path_nodes(),
            "schedule_notes": None,
            "created_at": "2024-01-01T00:00:00Z",
        }

    def _build_stage_schedules(
        self, project_start: date
    ) -> tuple[list[dict], date, date]:
        """Build per-stage planned and actual schedule entries."""
        schedules = []
        planned_cursor = project_start
        actual_cursor = project_start

        for stage_id in self._topo_order:
            if stage_id not in self._durations:
                continue

            base = self._durations[stage_id]
            factor_planned = self.rng.uniform(*STAGE_DURATION_VARIANCE)
            planned_days = max(1, round(base * factor_planned))

            # Actual: add some delay on top of planned
            delay_factor = 1.0 + self.rng.choices(
                [0, 0.1, 0.25, 0.5, 1.0],
                weights=[0.55, 0.20, 0.12, 0.08, 0.05],
                k=1,
            )[0]
            actual_days = max(1, round(planned_days * delay_factor))

            planned_end = planned_cursor + timedelta(days=planned_days)
            actual_end  = actual_cursor  + timedelta(days=actual_days)

            schedules.append({
                "stage_id": stage_id,
                "stage_name": stage_id.replace("_", " ").title(),
                "planned_start_date": planned_cursor.isoformat(),
                "planned_end_date": planned_end.isoformat(),
                "planned_duration_days": planned_days,
                "actual_start_date": actual_cursor.isoformat(),
                "actual_end_date": actual_end.isoformat(),
                "actual_duration_days": actual_days,
                "delay_days": max(0, actual_days - planned_days),
                "delay_reason": (
                    self.rng.choice(_DELAY_CATEGORIES)
                    if actual_days > planned_days else None
                ),
                "completion_percent": 100.0,
                "notes": None,
            })

            planned_cursor = planned_end
            actual_cursor  = actual_end

        return schedules, planned_cursor, actual_cursor

    def _build_delay_breakdown(self, total_delay: int) -> list[dict]:
        if total_delay == 0:
            return []

        remaining = total_delay
        breakdown = []
        cats = list(zip(_DELAY_CATEGORIES, _DELAY_WEIGHTS))
        self.rng.shuffle(cats)

        for cat, weight in cats:
            if remaining <= 0:
                break
            days = round(total_delay * weight)
            days = min(days, remaining)
            if days > 0:
                breakdown.append({
                    "category": cat,
                    "days_lost": days,
                    "percent_of_total": round(days / total_delay * 100, 1),
                })
                remaining -= days

        if remaining > 0 and breakdown:
            breakdown[-1]["days_lost"] += remaining
            breakdown[-1]["percent_of_total"] = round(
                breakdown[-1]["days_lost"] / total_delay * 100, 1
            )

        return breakdown
