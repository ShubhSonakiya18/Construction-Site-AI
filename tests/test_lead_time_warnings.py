"""
tests/test_lead_time_warnings.py — Sprint 12 Deliverable 4/7: pure-function
tests for compute_lead_time_warning() against small hand-built fixtures,
matching tests/test_critical_path.py's "small, hand-verifiable" approach —
no database, no app fixtures needed for any test in this file.
"""
from __future__ import annotations

from datetime import date

from app.services.inventory_service import compute_lead_time_warning


class FakeItem:
    def __init__(self, material_name, typical_lead_time_days, applicable_stage_id):
        self.material_name = material_name
        self.typical_lead_time_days = typical_lead_time_days
        self.applicable_stage_id = applicable_stage_id


class FakeTask:
    def __init__(self, stage_id, planned_start_date):
        self.stage_id = stage_id
        self.planned_start_date = planned_start_date


class TestNoWarningCases:
    def test_no_lead_time_configured_returns_none(self):
        item = FakeItem("Cement bags", None, "foundation")
        task = FakeTask("foundation", date(2026, 6, 1))
        result = compute_lead_time_warning(
            item, task, has_open_covering_order=False, as_of=date(2026, 6, 1)
        )
        assert result is None

    def test_no_applicable_stage_returns_none(self):
        item = FakeItem("Cement bags", 14, None)
        task = FakeTask("foundation", date(2026, 6, 1))
        result = compute_lead_time_warning(
            item, task, has_open_covering_order=False, as_of=date(2026, 6, 1)
        )
        assert result is None

    def test_no_matching_task_returns_none(self):
        item = FakeItem("Cement bags", 14, "foundation")
        result = compute_lead_time_warning(
            item, None, has_open_covering_order=False, as_of=date(2026, 6, 1)
        )
        assert result is None

    def test_open_covering_order_suppresses_warning(self):
        """A submitted/delivered PO already covers this material -- even
        if the order window has passed, no warning is needed since a
        human already acted on it."""
        item = FakeItem("Cement bags", 14, "foundation")
        task = FakeTask("foundation", date(2026, 6, 1))
        result = compute_lead_time_warning(
            item, task, has_open_covering_order=True, as_of=date(2026, 6, 1)
        )
        assert result is None

    def test_well_before_order_window_returns_none(self):
        """Stage starts in 60 days, lead time is 14 days -- comfortably
        early, no warning yet."""
        item = FakeItem("Cement bags", 14, "foundation")
        task = FakeTask("foundation", date(2026, 8, 1))
        result = compute_lead_time_warning(
            item, task, has_open_covering_order=False, as_of=date(2026, 6, 1)
        )
        assert result is None


class TestWarningCases:
    def test_exactly_on_order_by_date_warns_order_today(self):
        # planned_start_date=Jun 15, lead_time=14 -> order_by_date=Jun 1.
        item = FakeItem("Cement bags", 14, "foundation")
        task = FakeTask("foundation", date(2026, 6, 15))
        result = compute_lead_time_warning(
            item, task, has_open_covering_order=False, as_of=date(2026, 6, 1)
        )
        assert result is not None
        assert result.status == "order_now"
        assert result.order_by_date == date(2026, 6, 1)
        assert result.days_until_stage_start == 14
        assert "cement bags" in result.message.lower()
        assert "foundation" in result.message.lower()

    def test_past_order_by_date_warns_with_days_late(self):
        # order_by_date=Jun 1, as_of=Jun 4 -> 3 days late.
        item = FakeItem("Cement bags", 14, "foundation")
        task = FakeTask("foundation", date(2026, 6, 15))
        result = compute_lead_time_warning(
            item, task, has_open_covering_order=False, as_of=date(2026, 6, 4)
        )
        assert result is not None
        assert result.status == "order_now"
        assert "3 day" in result.message

    def test_message_names_the_material_and_stage(self):
        item = FakeItem("Countertops", 21, "cabinets_and_countertops")
        task = FakeTask("cabinets_and_countertops", date(2026, 6, 21))
        result = compute_lead_time_warning(
            item, task, has_open_covering_order=False, as_of=date(2026, 6, 1)
        )
        assert result is not None
        assert "Countertops" in result.message
        assert "cabinets_and_countertops" in result.message

    def test_stage_id_on_warning_matches_task(self):
        item = FakeItem("Rebar", 10, "foundation")
        task = FakeTask("foundation", date(2026, 6, 10))
        result = compute_lead_time_warning(
            item, task, has_open_covering_order=False, as_of=date(2026, 6, 1)
        )
        assert result is not None
        assert result.stage_id == "foundation"
