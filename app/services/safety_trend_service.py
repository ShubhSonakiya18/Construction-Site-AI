"""
app/services/safety_trend_service.py — Sprint 15, Deliverable 4: safety
proactive-warning computation.

Pure computation, no AI/LLM call — matching schedule_service.py/
cost_service.py's ADR-048 posture exactly. "Proactive warning" here means
a computed field on a read, not a pushed notification (docs/NEXT_SPRINT.md,
same resolution Sprint 14's "budget variance alert" already reached):
this codebase has no scheduler and no notification infrastructure, and
building one is a separate, much larger decision than this deliverable.

Session-free (unlike app/services/worker_matching.py's session-bound
DB lookup) — takes already-fetched values and computes over them, the
same split cost_service.py/schedule_service.py use between the
database-facing repository layer and the pure decision logic here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

# OSHA's own incidence-rate formula constant: cases per 100 full-time
# workers, based on a 40hr/week, 50-week work-year (2,000 hours/worker)
# scaled to 100 workers (200,000 hours). This is OSHA's real published
# constant, not a project-specific choice.
_OSHA_INCIDENCE_RATE_HOURS_BASE = 200_000

# Below this many logged hours, a computed incidence rate is more
# misleadingly precise than informative -- extrapolating "cases per 100
# workers" from a handful of logged hours produces a rate that swings
# wildly on one more or fewer incident. 1,000 hours is a deliberately
# conservative floor (roughly 25 worker-weeks), not an OSHA-defined
# threshold -- OSHA's formula has no minimum sample size of its own; this
# is this project's own judgment call about when to show the number.
_MINIMUM_HOURS_FOR_RELIABLE_RATE = 1_000


class LogHazardLike:
    """Structural type only (not a real base class) documenting what
    compute_unresolved_hazard_warnings() needs from a "hazard" —
    satisfied by the real LogHazard ORM model without importing it
    here, keeping this module database-free. Same PEP 544 duck-typing
    pattern as schedule_service.py's ScheduleTaskLike."""

    hazard_type: str
    severity: str
    description: str


@dataclass
class UnresolvedHazardWarning:
    hazard_type: str
    severity: str
    description: str
    days_open: int


@dataclass
class SafetyProactiveWarnings:
    """A read-time snapshot of safety signals worth a human's attention
    right now -- never persisted, recomputed on every read, same
    pattern as Sprint 11's schedule variance and Sprint 12's lead-time
    warnings.
    """

    unresolved_hazards: list[UnresolvedHazardWarning]
    days_since_last_incident: Optional[int]
    incidence_rate_per_200k_hours: Optional[float]
    incidence_rate_unavailable_reason: Optional[str]


def compute_unresolved_hazard_warnings(
    hazards_with_dates: list[tuple[LogHazardLike, date]], *, as_of: date
) -> list[UnresolvedHazardWarning]:
    """Turn (LogHazard, log_date) pairs into warnings with computed age,
    highest severity and oldest first -- a critical hazard open for 30
    days is a bigger warning than a low-severity one open for 2.
    """
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    warnings = [
        UnresolvedHazardWarning(
            hazard_type=hazard.hazard_type,
            severity=hazard.severity,
            description=hazard.description,
            days_open=(as_of - log_date).days,
        )
        for hazard, log_date in hazards_with_dates
    ]
    warnings.sort(key=lambda w: (severity_rank.get(w.severity, 99), -w.days_open))
    return warnings


def compute_days_since_last_incident(
    most_recent_incident_date: Optional[date], *, as_of: date
) -> Optional[int]:
    """None means the project has never recorded a safety incident at
    all -- distinct from 0 (an incident today), so a caller doesn't
    mistake "no history" for "incident-free today"."""
    if most_recent_incident_date is None:
        return None
    return (as_of - most_recent_incident_date).days


def compute_incidence_rate(
    *, recordable_incident_count: int, total_hours_worked: float
) -> tuple[Optional[float], Optional[str]]:
    """OSHA's standard incidence rate: (recordable_cases x 200,000) /
    hours_worked -- "recordable cases per 100 full-time workers per
    year," the industry-standard comparison figure.

    Returns (rate, unavailable_reason). unavailable_reason is set (rate
    is None) rather than computing and returning a number in two cases:
    zero hours logged (a real divide-by-zero, not just an edge case --
    happens whenever total_man_hours_worked was never extracted on any
    approved log), or hours below _MINIMUM_HOURS_FOR_RELIABLE_RATE
    (docs/NEXT_SPRINT.md's own caution: "decide whether hours_worked's
    aggregate ... is too incomplete to support a real OSHA
    incidence-rate calculation without overstating precision" --
    resolved here by refusing to show a rate the sample size can't
    support, rather than showing a technically-correct but misleading
    one).
    """
    if total_hours_worked <= 0:
        return None, "no logged hours worked to compute a rate from"
    if total_hours_worked < _MINIMUM_HOURS_FOR_RELIABLE_RATE:
        return None, (
            f"only {total_hours_worked:.0f} hours logged -- too few to compute a "
            "reliable incidence rate"
        )
    rate = (recordable_incident_count * _OSHA_INCIDENCE_RATE_HOURS_BASE) / total_hours_worked
    return round(rate, 2), None
