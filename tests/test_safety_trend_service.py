"""
tests/test_safety_trend_service.py — Sprint 15, Deliverable 4:
app/services/safety_trend_service.py.

Pure-function tests, no database -- same approach
tests/test_critical_path.py (Sprint 11) and
tests/test_lead_time_warnings.py (Sprint 12) take for their own
session-free service modules.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.services.safety_trend_service import (
    compute_days_since_last_incident,
    compute_incidence_rate,
    compute_unresolved_hazard_warnings,
)


@dataclass
class _Hazard:
    hazard_type: str
    severity: str
    description: str


class TestComputeUnresolvedHazardWarnings:
    def test_empty_input_yields_empty_list(self):
        assert compute_unresolved_hazard_warnings([], as_of=date(2026, 9, 1)) == []

    def test_days_open_computed_from_log_date_to_as_of(self):
        hazard = _Hazard("trip_hazard", "medium", "Loose cabling")
        warnings = compute_unresolved_hazard_warnings(
            [(hazard, date(2026, 8, 20))], as_of=date(2026, 9, 1),
        )
        assert warnings[0].days_open == 12

    def test_sorted_by_severity_first_critical_before_low(self):
        low = _Hazard("trip_hazard", "low", "Minor")
        critical = _Hazard("electrical_hazard", "critical", "Exposed wiring")
        warnings = compute_unresolved_hazard_warnings(
            [(low, date(2026, 8, 25)), (critical, date(2026, 8, 30))],
            as_of=date(2026, 9, 1),
        )
        assert warnings[0].severity == "critical"
        assert warnings[1].severity == "low"

    def test_within_the_same_severity_oldest_first(self):
        newer = _Hazard("trip_hazard", "high", "Newer")
        older = _Hazard("fall_risk", "high", "Older")
        warnings = compute_unresolved_hazard_warnings(
            [(newer, date(2026, 8, 30)), (older, date(2026, 8, 10))],
            as_of=date(2026, 9, 1),
        )
        assert warnings[0].description == "Older"
        assert warnings[0].days_open > warnings[1].days_open

    def test_unknown_severity_sorts_last_rather_than_crashing(self):
        unknown = _Hazard("other", "not_a_real_severity", "Weird data")
        known = _Hazard("trip_hazard", "low", "Known")
        warnings = compute_unresolved_hazard_warnings(
            [(unknown, date(2026, 8, 25)), (known, date(2026, 8, 25))],
            as_of=date(2026, 9, 1),
        )
        assert warnings[-1].description == "Weird data"


class TestComputeDaysSinceLastIncident:
    def test_none_when_no_incidents_ever_recorded(self):
        assert compute_days_since_last_incident(None, as_of=date(2026, 9, 1)) is None

    def test_zero_when_incident_was_today(self):
        assert compute_days_since_last_incident(
            date(2026, 9, 1), as_of=date(2026, 9, 1),
        ) == 0

    def test_positive_count_for_a_past_incident(self):
        assert compute_days_since_last_incident(
            date(2026, 8, 1), as_of=date(2026, 9, 1),
        ) == 31


class TestComputeIncidenceRate:
    def test_no_hours_yields_no_rate(self):
        rate, reason = compute_incidence_rate(
            recordable_incident_count=2, total_hours_worked=0.0,
        )
        assert rate is None
        assert reason is not None

    def test_below_minimum_hours_yields_no_rate(self):
        rate, reason = compute_incidence_rate(
            recordable_incident_count=1, total_hours_worked=500.0,
        )
        assert rate is None
        assert "too few" in reason

    def test_zero_incidents_with_enough_hours_yields_zero_rate(self):
        """A real, reportable zero -- a project with plenty of logged
        hours and no recordable incidents has a genuinely computable
        (and good) rate, not an unavailable one."""
        rate, reason = compute_incidence_rate(
            recordable_incident_count=0, total_hours_worked=5000.0,
        )
        assert rate == 0.0
        assert reason is None

    def test_standard_osha_formula(self):
        """OSHA's own worked example: 5 recordable cases, 500,000 hours
        worked -> (5 x 200,000) / 500,000 = 2.0."""
        rate, reason = compute_incidence_rate(
            recordable_incident_count=5, total_hours_worked=500_000.0,
        )
        assert rate == 2.0
        assert reason is None

    def test_rate_rounds_to_two_decimal_places(self):
        rate, _ = compute_incidence_rate(
            recordable_incident_count=1, total_hours_worked=3000.0,
        )
        assert rate == round((1 * 200_000) / 3000.0, 2)
