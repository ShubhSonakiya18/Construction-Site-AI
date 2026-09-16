"""
tests/test_cost_estimation.py — Sprint 17: app/services/cost_estimation_service.py.

Exercises the real knowledge/cost_estimation_reference.json and
knowledge/construction_ontology.json files (not hand-built fixtures) since
this service's entire job is combining those two real reference files --
a test that mocked them out would not be testing the thing that actually
ships. Matches the precedent of tests/test_critical_path.py (Sprint 11),
which also reads the real knowledge/dependency_graph.json rather than a
synthetic stand-in, because that file's real shape is exactly what the
computation has to handle correctly.
"""
from __future__ import annotations

import pytest

from app.services.cost_estimation_service import (
    compute_project_cost_estimate,
)

# The real seeded sample project's schedule -- all 23 dependency_graph.json
# stage ids, in sequence order, exactly as Sprint 11 seeds every new
# ProjectSchedule. Kept here as a literal (not re-derived from the knowledge
# file) so this test also catches an accidental stage_id rename anywhere in
# the pipeline.
FULL_PROJECT_SCHEDULE_STAGE_IDS = [
    "site_preparation", "foundation", "concrete_flatwork", "framing",
    "milestone_dried_in", "roofing", "electrical_rough_in", "hvac_rough_in",
    "plumbing_rough_in", "milestone_rough_in_complete", "insulation",
    "drywall", "painting", "tile_work", "cabinets_and_countertops",
    "flooring", "trim_and_millwork", "plumbing_finish", "electrical_finish",
    "hvac_finish", "punch_list", "inspection", "project_closeout",
]


class TestMissingProjectSize:
    def test_none_size_returns_clear_reason_not_a_fabricated_estimate(self):
        result = compute_project_cost_estimate(
            project_size_sqft=None,
            stage_ids=FULL_PROJECT_SCHEDULE_STAGE_IDS,
        )
        assert result.unavailable_reason is not None
        assert "project_size_sqft" in result.unavailable_reason
        assert result.low_usd == 0.0
        assert result.high_usd == 0.0
        assert result.stages == []

    def test_zero_size_is_treated_the_same_as_missing(self):
        result = compute_project_cost_estimate(
            project_size_sqft=0,
            stage_ids=FULL_PROJECT_SCHEDULE_STAGE_IDS,
        )
        assert result.unavailable_reason is not None


class TestRealReferenceDataComputation:
    """Against the real knowledge/cost_estimation_reference.json +
    knowledge/construction_ontology.json files -- see module docstring."""

    def test_full_schedule_produces_a_positive_total_range(self):
        result = compute_project_cost_estimate(
            project_size_sqft=2850,
            stage_ids=FULL_PROJECT_SCHEDULE_STAGE_IDS,
        )
        assert result.unavailable_reason is None
        assert result.low_usd > 0
        assert result.high_usd > result.low_usd
        # 9 stages have reference materials data; the other 14 (punch_list,
        # inspection, milestones, etc.) contribute nothing, not a fabricated
        # figure (ADR-065).
        assert len(result.stages) == 9

    def test_stage_with_no_reference_data_is_skipped_not_zero_filled(self):
        result = compute_project_cost_estimate(
            project_size_sqft=1000,
            stage_ids=["punch_list", "inspection", "site_preparation"],
        )
        assert result.stages == []
        assert result.low_usd == 0.0
        assert result.high_usd == 0.0

    def test_unknown_stage_id_is_silently_ignored(self):
        """A stage_id this project's real schedule holds that isn't in
        either knowledge file (shouldn't happen, but must not crash) is
        treated the same as a stage with no reference data."""
        result = compute_project_cost_estimate(
            project_size_sqft=1000,
            stage_ids=["not_a_real_stage"],
        )
        assert result.stages == []

    def test_quantity_scales_linearly_with_square_footage(self):
        small = compute_project_cost_estimate(
            project_size_sqft=1000, stage_ids=["foundation"],
        )
        large = compute_project_cost_estimate(
            project_size_sqft=2000, stage_ids=["foundation"],
        )
        assert large.low_usd == pytest.approx(small.low_usd * 2, rel=1e-6)
        assert large.high_usd == pytest.approx(small.high_usd * 2, rel=1e-6)

    def test_foundation_stage_includes_concrete_and_rebar(self):
        result = compute_project_cost_estimate(
            project_size_sqft=1000, stage_ids=["foundation"],
        )
        assert len(result.stages) == 1
        material_names = {m.material_name for m in result.stages[0].materials}
        assert "Ready-Mix Concrete" in material_names
        assert "Rebar #4 (1/2 inch)" in material_names


class TestContractComparisonNote:
    def test_no_note_when_contract_value_not_provided(self):
        result = compute_project_cost_estimate(
            project_size_sqft=2850,
            stage_ids=FULL_PROJECT_SCHEDULE_STAGE_IDS,
        )
        assert result.contract_comparison_note is None

    def test_note_says_above_when_contract_value_exceeds_the_range(self):
        result = compute_project_cost_estimate(
            project_size_sqft=2850,
            stage_ids=FULL_PROJECT_SCHEDULE_STAGE_IDS,
            contract_value_usd=425000,
        )
        assert result.contract_comparison_note is not None
        assert "above" in result.contract_comparison_note

    def test_note_says_below_when_contract_value_is_under_the_range(self):
        result = compute_project_cost_estimate(
            project_size_sqft=2850,
            stage_ids=FULL_PROJECT_SCHEDULE_STAGE_IDS,
            contract_value_usd=1000,
        )
        assert result.contract_comparison_note is not None
        assert "below" in result.contract_comparison_note

    def test_note_says_within_when_contract_value_falls_inside_the_range(self):
        # Compute the real range first, then pick a contract value inside it.
        estimate = compute_project_cost_estimate(
            project_size_sqft=2850,
            stage_ids=FULL_PROJECT_SCHEDULE_STAGE_IDS,
        )
        midpoint = (estimate.low_usd + estimate.high_usd) / 2
        result = compute_project_cost_estimate(
            project_size_sqft=2850,
            stage_ids=FULL_PROJECT_SCHEDULE_STAGE_IDS,
            contract_value_usd=midpoint,
        )
        assert result.contract_comparison_note is not None
        assert "within" in result.contract_comparison_note

    def test_zero_or_none_contract_value_produces_no_note(self):
        result = compute_project_cost_estimate(
            project_size_sqft=1000, stage_ids=["foundation"], contract_value_usd=0,
        )
        assert result.contract_comparison_note is None


class TestReferenceFileIntegrity:
    """Guards against the reference file drifting out of sync with the
    real ontology/dependency-graph ids it's keyed against -- the same
    class of bug the pre-Sprint-15 extraction prompt bug was (field names
    that silently stopped matching the real schema)."""

    def test_every_referenced_material_id_exists_in_the_ontology(self):
        import json
        from pathlib import Path

        from dataset_generation_framework.core.knowledge_loader import (
            KnowledgeBase,
        )

        ref_path = (
            Path(__file__).resolve().parent.parent
            / "knowledge"
            / "cost_estimation_reference.json"
        )
        with open(ref_path, "r", encoding="utf-8") as f:
            reference = json.load(f)

        kb = KnowledgeBase()
        valid_material_ids = {m["id"] for m in kb.ontology_materials()}

        for stage in reference["stages"]:
            for entry in stage["materials"]:
                assert entry["material_id"] in valid_material_ids, (
                    f"{entry['material_id']} in stage {stage['stage_id']} "
                    "is not a real ontology material id"
                )

    def test_every_referenced_stage_id_exists_in_the_dependency_graph(self):
        import json
        from pathlib import Path

        from dataset_generation_framework.core.knowledge_loader import (
            KnowledgeBase,
        )

        ref_path = (
            Path(__file__).resolve().parent.parent
            / "knowledge"
            / "cost_estimation_reference.json"
        )
        with open(ref_path, "r", encoding="utf-8") as f:
            reference = json.load(f)

        kb = KnowledgeBase()
        valid_stage_ids = {n["id"] for n in kb.dag_nodes()}

        for stage in reference["stages"]:
            assert stage["stage_id"] in valid_stage_ids, (
                f"{stage['stage_id']} is not a real dependency_graph.json "
                "stage id"
            )
