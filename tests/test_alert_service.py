"""
tests/test_alert_service.py — Sprint 19: app/services/alert_service.py.

Pure-function tests against small hand-built inputs, no database, no
Celery -- the same approach tests/test_cost_computation.py and
tests/test_safety_trend_service.py take for their own session-free
service modules.

This is the real guarantee that a project doesn't get emailed the same
alert every scheduler tick forever, and that a real status transition
(worse news) is never silently suppressed by the cooldown (ADR-066).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.alert_service import (
    ALERT_COOLDOWN,
    should_send_budget_alert,
    should_send_safety_alert,
)

NOW = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)


class TestShouldSendBudgetAlert:
    def test_on_track_never_alerts(self):
        decision = should_send_budget_alert(
            current_status="on_track",
            last_sent_status=None,
            last_sent_at=None,
            now=NOW,
        )
        assert decision.should_send is False

    def test_no_budget_set_never_alerts(self):
        decision = should_send_budget_alert(
            current_status="no_budget_set",
            last_sent_status=None,
            last_sent_at=None,
            now=NOW,
        )
        assert decision.should_send is False

    def test_first_ever_over_budget_alerts_immediately(self):
        decision = should_send_budget_alert(
            current_status="over_budget",
            last_sent_status=None,
            last_sent_at=None,
            now=NOW,
        )
        assert decision.should_send is True
        assert decision.new_status_value == "over_budget"

    def test_same_status_within_cooldown_does_not_resend(self):
        decision = should_send_budget_alert(
            current_status="over_budget",
            last_sent_status="over_budget",
            last_sent_at=NOW - timedelta(hours=1),
            now=NOW,
        )
        assert decision.should_send is False

    def test_same_status_after_cooldown_resends(self):
        decision = should_send_budget_alert(
            current_status="over_budget",
            last_sent_status="over_budget",
            last_sent_at=NOW - ALERT_COOLDOWN - timedelta(minutes=1),
            now=NOW,
        )
        assert decision.should_send is True
        assert decision.new_status_value == "over_budget"

    def test_worsening_transition_alerts_immediately_regardless_of_cooldown(self):
        """approaching_budget -> over_budget must never be suppressed by
        the cooldown, even seconds after the last alert -- ADR-066."""
        decision = should_send_budget_alert(
            current_status="over_budget",
            last_sent_status="approaching_budget",
            last_sent_at=NOW - timedelta(minutes=1),
            now=NOW,
        )
        assert decision.should_send is True
        assert decision.new_status_value == "over_budget"

    def test_transition_back_to_on_track_does_not_alert(self):
        """Going back to on_track is not itself an alert-worthy event in
        this sprint's scope (a "you're back on track" email is a real,
        separate design question left to future scope)."""
        decision = should_send_budget_alert(
            current_status="on_track",
            last_sent_status="over_budget",
            last_sent_at=NOW - timedelta(minutes=1),
            now=NOW,
        )
        assert decision.should_send is False


class TestShouldSendSafetyAlert:
    def test_no_hazards_never_alerts(self):
        decision = should_send_safety_alert(
            has_unresolved_hazards=False,
            last_sent_status=None,
            last_sent_at=None,
            now=NOW,
        )
        assert decision.should_send is False

    def test_first_ever_hazard_alerts_immediately(self):
        decision = should_send_safety_alert(
            has_unresolved_hazards=True,
            last_sent_status=None,
            last_sent_at=None,
            now=NOW,
        )
        assert decision.should_send is True
        assert decision.new_status_value == "has_hazards"

    def test_persisting_hazard_within_cooldown_does_not_resend(self):
        decision = should_send_safety_alert(
            has_unresolved_hazards=True,
            last_sent_status="has_hazards",
            last_sent_at=NOW - timedelta(hours=1),
            now=NOW,
        )
        assert decision.should_send is False

    def test_persisting_hazard_after_cooldown_resends(self):
        decision = should_send_safety_alert(
            has_unresolved_hazards=True,
            last_sent_status="has_hazards",
            last_sent_at=NOW - ALERT_COOLDOWN - timedelta(minutes=1),
            now=NOW,
        )
        assert decision.should_send is True

    def test_hazards_resolved_does_not_alert(self):
        decision = should_send_safety_alert(
            has_unresolved_hazards=False,
            last_sent_status="has_hazards",
            last_sent_at=NOW - timedelta(minutes=1),
            now=NOW,
        )
        assert decision.should_send is False

    def test_new_hazard_after_being_clear_alerts_immediately(self):
        """A hazard reappearing after a prior 'clear' send should alert
        right away, not wait out a cooldown that was never started for
        the "has_hazards" status in the first place."""
        decision = should_send_safety_alert(
            has_unresolved_hazards=True,
            last_sent_status="clear",
            last_sent_at=NOW - timedelta(minutes=1),
            now=NOW,
        )
        assert decision.should_send is True
        assert decision.new_status_value == "has_hazards"
