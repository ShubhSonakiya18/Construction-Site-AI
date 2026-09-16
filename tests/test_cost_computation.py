"""
tests/test_cost_computation.py — Sprint 14: app/services/cost_service.py.

Pure-function tests against small hand-built dicts, no database — the same
approach tests/test_critical_path.py (Sprint 11) and
tests/test_lead_time_warnings.py (Sprint 12) take for their own session-free
service modules.

The arithmetic here is deliberately not delegated to the LLM (ADR-058), so
these tests are the real guarantee that daily totals, running totals, and
budget status are right.
"""
from __future__ import annotations

from datetime import date

from app.services.cost_service import (
    APPROACHING_BUDGET_THRESHOLD,
    build_cost_trend,
    compute_budget_variance,
)


class TestBuildCostTrend:
    def test_empty_input_yields_empty_series(self):
        assert build_cost_trend([]) == []

    def test_daily_total_sums_the_four_components(self):
        points = build_cost_trend([
            (date(2026, 5, 1), {
                "daily_labor_cost_usd": 2000,
                "daily_material_cost_usd": 500,
                "daily_equipment_cost_usd": 150,
                "daily_subcontractor_cost_usd": 350,
            }),
        ])
        assert points[0].daily_total_cost_usd == 3000.0

    def test_missing_components_contribute_zero_without_nulling_the_total(self):
        """A log reporting only labor has a real, if partial, daily total
        -- the unreported components stay null on the point itself so a
        reader can tell "not reported" from "reported as $0"."""
        points = build_cost_trend([
            (date(2026, 5, 1), {"daily_labor_cost_usd": 1200}),
        ])
        assert points[0].daily_total_cost_usd == 1200.0
        assert points[0].daily_labor_cost_usd == 1200.0
        assert points[0].daily_material_cost_usd is None
        assert points[0].daily_equipment_cost_usd is None
        assert points[0].daily_subcontractor_cost_usd is None

    def test_explicit_zero_is_preserved_and_distinct_from_null(self):
        points = build_cost_trend([
            (date(2026, 5, 1), {
                "daily_labor_cost_usd": 1000,
                "daily_equipment_cost_usd": 0,
            }),
        ])
        assert points[0].daily_equipment_cost_usd == 0.0
        assert points[0].daily_material_cost_usd is None
        assert points[0].daily_total_cost_usd == 1000.0

    def test_cumulative_spend_accumulates_across_days(self):
        points = build_cost_trend([
            (date(2026, 5, 1), {"daily_labor_cost_usd": 1000}),
            (date(2026, 5, 2), {"daily_labor_cost_usd": 1500}),
            (date(2026, 5, 3), {"daily_labor_cost_usd": 500, "daily_material_cost_usd": 250}),
        ])
        assert [p.cumulative_spend_to_date_usd for p in points] == [1000.0, 2500.0, 3250.0]
        assert [p.daily_total_cost_usd for p in points] == [1000.0, 1500.0, 750.0]

    def test_ignores_the_derived_keys_even_if_somehow_present(self):
        """ADR-058 keeps daily_total_cost_usd out of the extraction
        prompt, but a hand-seeded or legacy row could still carry one --
        the computed sum always wins over whatever the JSON claims."""
        points = build_cost_trend([
            (date(2026, 5, 1), {
                "daily_labor_cost_usd": 100,
                "daily_material_cost_usd": 100,
                "daily_total_cost_usd": 99999,
            }),
        ])
        assert points[0].daily_total_cost_usd == 200.0


class TestComputeBudgetVariance:
    def test_no_contract_value_reports_no_budget_set(self):
        variance = compute_budget_variance(
            contract_value_usd=None, total_spend_to_date_usd=5000.0
        )
        assert variance.status == "no_budget_set"
        assert variance.budget_remaining_usd is None
        assert variance.percent_of_budget_spent is None
        # Spend is still reported -- only the comparison is unavailable.
        assert variance.total_spend_to_date_usd == 5000.0

    def test_zero_contract_value_is_treated_as_unset_not_as_instantly_over(self):
        """A $0 contract value is far more likely to be missing data than
        a real zero-value project, and reporting 'over_budget' for it
        would be a false alarm on every such project."""
        variance = compute_budget_variance(
            contract_value_usd=0.0, total_spend_to_date_usd=100.0
        )
        assert variance.status == "no_budget_set"

    def test_on_track_well_under_budget(self):
        variance = compute_budget_variance(
            contract_value_usd=100_000.0, total_spend_to_date_usd=40_000.0
        )
        assert variance.status == "on_track"
        assert variance.budget_remaining_usd == 60_000.0
        assert variance.percent_of_budget_spent == 40.0

    def test_approaching_budget_at_the_threshold(self):
        at_threshold = 100_000.0 * APPROACHING_BUDGET_THRESHOLD
        variance = compute_budget_variance(
            contract_value_usd=100_000.0, total_spend_to_date_usd=at_threshold
        )
        assert variance.status == "approaching_budget"

    def test_just_under_the_threshold_is_still_on_track(self):
        variance = compute_budget_variance(
            contract_value_usd=100_000.0,
            total_spend_to_date_usd=100_000.0 * APPROACHING_BUDGET_THRESHOLD - 1,
        )
        assert variance.status == "on_track"

    def test_over_budget_reports_a_negative_remaining(self):
        variance = compute_budget_variance(
            contract_value_usd=100_000.0, total_spend_to_date_usd=112_500.0
        )
        assert variance.status == "over_budget"
        assert variance.budget_remaining_usd == -12_500.0
        assert variance.percent_of_budget_spent == 112.5

    def test_exactly_at_budget_is_not_yet_over(self):
        variance = compute_budget_variance(
            contract_value_usd=100_000.0, total_spend_to_date_usd=100_000.0
        )
        assert variance.status == "approaching_budget"
        assert variance.budget_remaining_usd == 0.0
