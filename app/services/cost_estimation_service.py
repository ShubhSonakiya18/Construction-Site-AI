"""
app/services/cost_estimation_service.py — Sprint 17: reference-cost range
estimate for a project, from typical-quantity reference data.

Pure computation, no AI/LLM call — the same ADR-005/007/048 posture as
app/services/cost_service.py (Sprint 14), app/services/schedule_service.py
(Sprint 11), and app/services/safety_trend_service.py (Sprint 15).
Multiplying a typical quantity-per-1000-sqft figure by a project's real
square footage, then by the ontology's own cost-per-unit range, is
arithmetic — there is nothing here an LLM would do better.

This is explicitly NOT a bid, NOT a quote, and NOT a historical-data-driven
prediction (ADR-065) — every output is a reference-range estimate computed
from knowledge/cost_estimation_reference.json's typical-quantity figures and
knowledge/construction_ontology.json's material cost ranges (via
dataset_generation_framework.core.knowledge_loader.KnowledgeBase.ontology_materials(),
the same accessor Sprint 1 already exposes for that file). Materials-only —
no labor-hour figure exists anywhere in this codebase to build one from
(ADR-065).

Session-free for the same reason cost_service.py and schedule_service.py
are: tests/test_cost_estimation.py can exercise the arithmetic against a
small hand-built reference table without a database or the real knowledge
files.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("app.services.cost_estimation")

_REFERENCE_FILE = (
    Path(__file__).resolve().parent.parent.parent
    / "knowledge"
    / "cost_estimation_reference.json"
)


@dataclass
class MaterialEstimateLine:
    """One material's estimated quantity and cost range for a stage."""

    material_id: str
    material_name: str
    unit: str
    estimated_quantity: float
    low_usd: float
    high_usd: float


@dataclass
class StageEstimate:
    """One stage's aggregated materials-only cost range."""

    stage_id: str
    materials: list[MaterialEstimateLine]
    low_usd: float
    high_usd: float


@dataclass
class ProjectCostEstimate:
    """The full project-level reference-cost estimate, or a clear reason
    none is available.

    unavailable_reason is set (and stages/low_usd/high_usd left empty/0)
    when project_size_sqft is missing -- the same missing-input-degrades-
    gracefully posture as compute_earned_value() returning None fields,
    never a fabricated estimate from an unknown size.
    """

    project_size_sqft: Optional[float]
    stages: list[StageEstimate]
    low_usd: float
    high_usd: float
    unavailable_reason: Optional[str]
    contract_comparison_note: Optional[str]


def _load_reference_data() -> dict:
    """Returns the parsed knowledge/cost_estimation_reference.json.

    Deferred, broad-except-free load matching the file's own role as
    static, read-only reference data (ADR-006) -- a missing file is a
    real deployment error, not something to silently degrade around, so
    it's allowed to raise rather than be swallowed.
    """
    with open(_REFERENCE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_material_cost_ranges() -> dict[str, tuple[float, float, str, str]]:
    """Returns {material_id: (low_usd_per_unit, high_usd_per_unit, unit, name)}
    from knowledge/construction_ontology.json via the Sprint 1 KnowledgeBase
    singleton's existing ontology_materials() accessor -- not a fresh direct
    file read, so this stays in sync with whatever KnowledgeBase already
    loads for every other consumer of that file.
    """
    from dataset_generation_framework.core.knowledge_loader import KnowledgeBase

    kb = KnowledgeBase()
    ranges: dict[str, tuple[float, float, str, str]] = {}
    for material in kb.ontology_materials():
        cost_range = material.get("cost_range_per_unit_usd")
        if not cost_range or len(cost_range) != 2:
            continue
        ranges[material["id"]] = (
            float(cost_range[0]),
            float(cost_range[1]),
            material.get("typical_unit", ""),
            material.get("name", material["id"]),
        )
    return ranges


def compute_project_cost_estimate(
    *,
    project_size_sqft: Optional[float],
    stage_ids: list[str],
    contract_value_usd: Optional[float] = None,
) -> ProjectCostEstimate:
    """Compute a materials-only reference-cost range for a project.

    stage_ids: the project's own real ScheduleTask.stage_id values
    (Sprint 11), not a fresh lookup of "all stages that exist" -- a
    project's actual stage list is what this estimate should cover, not
    the generic dependency graph's full 23-node set (a stage this
    project's schedule doesn't include, e.g. an optional stage skipped
    for this build, contributes nothing).

    contract_comparison_note is set only when contract_value_usd is
    provided -- a plain-language sanity-check sentence, never a claim
    the contract value is "right" or "wrong" (ADR-065's honesty
    boundary: this compares against a reference range, it does not
    validate a real signed number).
    """
    if project_size_sqft is None or project_size_sqft <= 0:
        return ProjectCostEstimate(
            project_size_sqft=project_size_sqft,
            stages=[],
            low_usd=0.0,
            high_usd=0.0,
            unavailable_reason=(
                "project_size_sqft is not set for this project -- a "
                "reference-cost estimate needs a square footage to scale "
                "typical material quantities against."
            ),
            contract_comparison_note=None,
        )

    reference = _load_reference_data()
    cost_ranges = _load_material_cost_ranges()
    reference_by_stage = {s["stage_id"]: s for s in reference["stages"]}
    size_factor = project_size_sqft / 1000.0

    stage_estimates: list[StageEstimate] = []
    total_low = 0.0
    total_high = 0.0

    for stage_id in stage_ids:
        stage_ref = reference_by_stage.get(stage_id)
        if stage_ref is None:
            # No materials reference data for this stage (e.g.
            # site_preparation, punch_list) -- not every stage has a
            # material-driven cost worth estimating (ADR-065). Skipped,
            # not zero-filled, so the stage simply contributes nothing
            # rather than implying "this stage costs $0."
            continue

        lines: list[MaterialEstimateLine] = []
        stage_low = 0.0
        stage_high = 0.0
        for entry in stage_ref["materials"]:
            material_id = entry["material_id"]
            cost_range = cost_ranges.get(material_id)
            if cost_range is None:
                logger.warning(
                    "cost_estimation_reference.json references unknown "
                    "material_id=%s -- skipped",
                    material_id,
                )
                continue
            low_per_unit, high_per_unit, unit, name = cost_range
            quantity = entry["typical_quantity_per_1000_sqft"] * size_factor
            low_usd = quantity * low_per_unit
            high_usd = quantity * high_per_unit
            lines.append(
                MaterialEstimateLine(
                    material_id=material_id,
                    material_name=name,
                    unit=unit,
                    estimated_quantity=round(quantity, 2),
                    low_usd=round(low_usd, 2),
                    high_usd=round(high_usd, 2),
                )
            )
            stage_low += low_usd
            stage_high += high_usd

        if lines:
            stage_estimates.append(
                StageEstimate(
                    stage_id=stage_id,
                    materials=lines,
                    low_usd=round(stage_low, 2),
                    high_usd=round(stage_high, 2),
                )
            )
            total_low += stage_low
            total_high += stage_high

    comparison_note: Optional[str] = None
    if contract_value_usd is not None and contract_value_usd > 0:
        if contract_value_usd < total_low:
            comparison_note = (
                f"The contract value (${contract_value_usd:,.0f}) is below "
                f"the reference materials estimate range "
                f"(${total_low:,.0f}-${total_high:,.0f})."
            )
        elif contract_value_usd > total_high:
            comparison_note = (
                f"The contract value (${contract_value_usd:,.0f}) is above "
                f"the reference materials estimate range "
                f"(${total_low:,.0f}-${total_high:,.0f})."
            )
        else:
            comparison_note = (
                f"The contract value (${contract_value_usd:,.0f}) falls "
                f"within the reference materials estimate range "
                f"(${total_low:,.0f}-${total_high:,.0f})."
            )

    return ProjectCostEstimate(
        project_size_sqft=project_size_sqft,
        stages=stage_estimates,
        low_usd=round(total_low, 2),
        high_usd=round(total_high, 2),
        unavailable_reason=None,
        contract_comparison_note=comparison_note,
    )
