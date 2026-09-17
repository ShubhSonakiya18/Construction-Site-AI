"""
app/services/alert_service.py — Sprint 19: alert dedup/cooldown decision
logic and the notification recipients query.

Pure decision function (should_send_alert), no session/Celery/email
dependency — the same shape app/services/cost_service.py and
app/services/safety_trend_service.py already established, so
tests/test_alert_service.py can exercise the cooldown/transition logic
against small hand-built inputs without a database. The database-facing
side (reading/writing ProjectAlertSent rows, finding recipients) is kept
at the edges, in app/tasks/alert_tasks.py.

See docs/DECISIONS.md ADR-066 for why a real status TRANSITION always
fires regardless of cooldown (worse news is never suppressed by a timer),
while the SAME bad status re-fires only after the cooldown window.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

# A convention, not a derived figure -- matching how Sprint 14's
# APPROACHING_BUDGET_THRESHOLD and Sprint 15's incidence-rate reliability
# floor are both documented as deliberate choices rather than hidden
# magic numbers (ADR-066).
ALERT_COOLDOWN = timedelta(hours=24)

# Statuses that warrant an alert at all. compute_budget_variance()'s
# "on_track"/"no_budget_set" and an all-clear safety status are
# deliberately never alert-worthy -- see should_send_alert()'s docstring.
ALERTABLE_BUDGET_STATUSES = frozenset({"approaching_budget", "over_budget"})


@dataclass
class AlertDecision:
    """Whether to send an alert right now, and what to record if so."""

    should_send: bool
    new_status_value: Optional[str] = None


def should_send_budget_alert(
    *,
    current_status: str,
    last_sent_status: Optional[str],
    last_sent_at: Optional[datetime],
    now: datetime,
) -> AlertDecision:
    """Decide whether a budget-variance alert should fire right now.

    current_status: this project's real, freshly-computed
        BudgetVariance.status (Sprint 14) -- "on_track" / "approaching_budget"
        / "over_budget" / "no_budget_set".
    last_sent_status / last_sent_at: the project's ProjectAlertSent row for
        alert_type="budget_variance", or both None if no alert has ever
        been sent for this project.

    "on_track" and "no_budget_set" never alert -- there is nothing
    proactive to say when a project is fine or has no budget configured
    to compare against. A transition INTO one of those from a bad status
    is also not alerted here (a "you're back on track" email is a real,
    separate design question Deliverable 1 explicitly left to future
    scope, not assumed).

    A real transition between two alertable statuses (e.g.
    approaching_budget -> over_budget) always fires, regardless of
    cooldown -- worse news must never be silently suppressed by a timer
    (ADR-066). The SAME status persisting only re-fires once
    ALERT_COOLDOWN has elapsed since the last send.
    """
    if current_status not in ALERTABLE_BUDGET_STATUSES:
        return AlertDecision(should_send=False)

    if last_sent_status is None or last_sent_at is None:
        return AlertDecision(should_send=True, new_status_value=current_status)

    if last_sent_status != current_status:
        return AlertDecision(should_send=True, new_status_value=current_status)

    if now - last_sent_at >= ALERT_COOLDOWN:
        return AlertDecision(should_send=True, new_status_value=current_status)

    return AlertDecision(should_send=False)


def should_send_safety_alert(
    *,
    has_unresolved_hazards: bool,
    last_sent_status: Optional[str],
    last_sent_at: Optional[datetime],
    now: datetime,
) -> AlertDecision:
    """Decide whether a safety-warning alert should fire right now.

    Unlike budget variance (a small, named enum of statuses), Sprint 15's
    safety_proactive_warnings is a set of independent signals (unresolved
    hazards, days-since-incident, incidence rate) with no single "status"
    string to diff -- collapsing it to a boolean
    ("does this project have at least one unresolved hazard right now")
    is deliberately the simplest honest signal Deliverable 1 could alert
    on for this sprint; a richer per-hazard-severity alert is real future
    scope, not attempted here (see docs/NEXT_SPRINT.md's own scoping).

    Same transition-always-fires / same-state-needs-cooldown shape as
    should_send_budget_alert(), using the fixed string "has_hazards" as
    the tracked status value so a transition to "no hazards" (which never
    alerts, same reasoning as budget's "on_track") is distinguishable
    from "still has hazards."
    """
    current_status = "has_hazards" if has_unresolved_hazards else "clear"

    if current_status == "clear":
        return AlertDecision(should_send=False)

    if last_sent_status is None or last_sent_at is None:
        return AlertDecision(should_send=True, new_status_value=current_status)

    if last_sent_status != current_status:
        return AlertDecision(should_send=True, new_status_value=current_status)

    if now - last_sent_at >= ALERT_COOLDOWN:
        return AlertDecision(should_send=True, new_status_value=current_status)

    return AlertDecision(should_send=False)


def utc_now() -> datetime:
    """Single source of "now" for alert decisions -- matches
    date.today()'s role in cost_service.py/safety_trend_service.py, kept
    as its own function so tests can pass an explicit `now` instead of
    depending on wall-clock time."""
    return datetime.now(timezone.utc)
