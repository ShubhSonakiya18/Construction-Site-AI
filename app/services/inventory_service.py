"""
app/services/inventory_service.py — Sprint 12: lead-time warning computation.

Pure computation, no AI/LLM call — matching app/services/schedule_service.py's
ADR-048 posture exactly ("no AI where deterministic logic suffices"). A
lead-time warning is date arithmetic over an InventoryItem's
typical_lead_time_days and the ScheduleTask it's cross-referenced against
via applicable_stage_id — the same "if this holds, here's what happens"
framing Sprint 11's delay-impact prediction uses, not generated prose.

The database-facing reconciliation logic (decrementing/incrementing
quantity_on_hand, creating auto-generated purchase orders) lives in
database/repositories/inventory.py, matching how Sprint 11 split
CPM/variance computation (schedule_service.py, session-free) from
schedule creation/persistence (repositories/schedule.py, session-bound).
This module stays session-free for the same reason: it's what makes
tests/test_lead_time_warnings.py able to test it against small hand-built
fixtures without a database, exactly like tests/test_critical_path.py
does for compute_critical_path().
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional


@dataclass
class LeadTimeWarning:
    """One inventory item's lead-time warning, or the lack of one."""

    material_name: str
    stage_id: str
    status: str  # "order_now" | "on_track" | "no_data"
    days_until_stage_start: Optional[int]
    order_by_date: Optional[date]
    message: str


class InventoryItemLike:
    """Structural type only (not a real base class) documenting what
    compute_lead_time_warning() needs from an "item" — satisfied by the
    real InventoryItem ORM model without importing it here, matching
    app/services/schedule_service.py's ScheduleTaskLike pattern."""

    material_name: str
    typical_lead_time_days: Optional[int]
    applicable_stage_id: Optional[str]


class ScheduleTaskLike:
    """Structural type for the ScheduleTask fields this module reads —
    see InventoryItemLike above for why this isn't a real base class."""

    stage_id: str
    planned_start_date: date


def compute_lead_time_warning(
    item: "InventoryItemLike",
    matching_task: Optional["ScheduleTaskLike"],
    *,
    has_open_covering_order: bool,
    as_of: date,
) -> Optional[LeadTimeWarning]:
    """Returns a warning if item needs to be ordered now to arrive before
    matching_task's planned start, or None if there's nothing to warn
    about (no lead time configured, no matching stage found, the order
    window hasn't opened yet, or an order is already placed).

    has_open_covering_order is the caller's responsibility to determine
    (does a submitted/delivered PO for this item already exist) — kept
    as a plain bool parameter rather than this function querying
    purchase_orders itself, so it stays a pure function testable without
    a database, matching schedule_service.py's compute_variance() and
    propagate_delay_impact() pattern.
    """
    if item.typical_lead_time_days is None or item.applicable_stage_id is None:
        return None
    if matching_task is None:
        return None
    if has_open_covering_order:
        return None

    order_by_date = _subtract_days(matching_task.planned_start_date, item.typical_lead_time_days)
    days_until_stage_start = (matching_task.planned_start_date - as_of).days

    if as_of <= order_by_date:
        # The order window hasn't closed yet -- either still comfortably
        # early, or right at the edge. Only warn once we're actually
        # inside the "must order now" window (as_of > order_by_date is
        # the overdue case below); being before it is on_track.
        if as_of == order_by_date:
            return LeadTimeWarning(
                material_name=item.material_name,
                stage_id=matching_task.stage_id,
                status="order_now",
                days_until_stage_start=days_until_stage_start,
                order_by_date=order_by_date,
                message=(
                    f"Order {item.material_name} today — "
                    f"{item.typical_lead_time_days}-day lead time, "
                    f"{matching_task.stage_id} starts in "
                    f"{days_until_stage_start} day(s)."
                ),
            )
        return None

    # as_of > order_by_date: the order window has already passed and no
    # covering order exists -- this is the "you're already late" case,
    # not just "order now."
    days_late = (as_of - order_by_date).days
    return LeadTimeWarning(
        material_name=item.material_name,
        stage_id=matching_task.stage_id,
        status="order_now",
        days_until_stage_start=days_until_stage_start,
        order_by_date=order_by_date,
        message=(
            f"Order {item.material_name} now — {days_late} day(s) past "
            f"the recommended order date for {matching_task.stage_id} "
            f"({item.typical_lead_time_days}-day lead time, stage starts "
            f"in {days_until_stage_start} day(s))."
        ),
    )


def _subtract_days(d: date, days: int) -> date:
    return d - timedelta(days=days)
