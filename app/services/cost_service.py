"""
app/services/cost_service.py — Sprint 14: cost totals and budget variance.

Pure computation, no AI/LLM call — matching app/services/schedule_service.py
and app/services/inventory_service.py's ADR-048 posture exactly ("no AI where
deterministic logic suffices"). Summing four cost components and comparing a
running total against a contract value is arithmetic; there is nothing here an
LLM would do better and much it would do worse (ADR-058 declines to ask the
model even to add the four components together).

Session-free for the same reason the other two service modules are: it makes
tests/test_cost_computation.py able to test the arithmetic against small
hand-built dicts without a database, exactly like tests/test_critical_path.py
does for compute_critical_path().

The database-facing side (fetching approved logs' financials, summing real
LogMaterialUsed line items) lives in database/repositories/daily_log.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

# Kept in sync with database/repositories/daily_log.py's COST_COMPONENT_FIELDS
# — the four figures ADR-058 asks the LLM for. Imported rather than
# redefined so the two can never drift.
from database.repositories.daily_log import COST_COMPONENT_FIELDS


@dataclass
class DailyCostPoint:
    """One approved log's cost figures on its date.

    daily_total_cost_usd is computed here as the sum of whichever
    components were reported — never read from the extracted JSON, which
    deliberately never contains it (ADR-058: no reason to trust an LLM's
    addition when the app can do it).
    """

    log_date: date
    daily_labor_cost_usd: Optional[float]
    daily_material_cost_usd: Optional[float]
    daily_equipment_cost_usd: Optional[float]
    daily_subcontractor_cost_usd: Optional[float]
    daily_total_cost_usd: float
    cumulative_spend_to_date_usd: float


@dataclass
class BudgetVariance:
    """Project-level budget position as of the most recent approved log.

    status is the "alert" Deliverable 2 calls for — a computed field on a
    read, not a pushed notification: this codebase has no scheduler and no
    notification infrastructure, and inventing one is a much larger
    decision than cost tracking (docs/NEXT_SPRINT.md, out of scope).
    """

    contract_value_usd: Optional[float]
    total_spend_to_date_usd: float
    budget_remaining_usd: Optional[float]
    percent_of_budget_spent: Optional[float]
    status: str  # on_track | approaching_budget | over_budget | no_budget_set


# A project that has spent this much of its contract value is flagged as
# approaching its budget. 90% is a convention, not a derived figure — see
# ADR-060 for why a fixed threshold is used rather than one scaled by
# schedule progress.
APPROACHING_BUDGET_THRESHOLD = 0.90


def _sum_reported(financials: dict) -> float:
    """Sum whichever of the four cost components were actually reported.

    A missing or null component contributes 0 to the total but does NOT
    make the total null — a log reporting only labor cost has a real,
    if partial, daily total. Distinguishing "reported $0" from "not
    reported" matters at the component level (both are preserved as-is on
    DailyCostPoint) but not for the sum.
    """
    total = 0.0
    for key in COST_COMPONENT_FIELDS:
        value = financials.get(key)
        if value is not None:
            total += float(value)
    return total


def build_cost_trend(
    financials_by_date: list[tuple[date, dict]],
) -> list[DailyCostPoint]:
    """Turn (log_date, financials dict) pairs — oldest first, as
    DailyLogRepository.get_daily_cost_trend_scoped() returns them — into
    a chronological series with per-day and running totals.

    cumulative_spend_to_date_usd is computed here rather than extracted
    (ADR-058: a single transcript has no way to know a running total
    across prior logs) and never persisted — the same read-time-only
    projection pattern Sprint 11's schedule variance and Sprint 12's
    lead-time warnings established.
    """
    points: list[DailyCostPoint] = []
    running = 0.0
    for log_date, financials in financials_by_date:
        daily_total = _sum_reported(financials)
        running += daily_total
        points.append(
            DailyCostPoint(
                log_date=log_date,
                daily_labor_cost_usd=_opt_float(financials.get("daily_labor_cost_usd")),
                daily_material_cost_usd=_opt_float(
                    financials.get("daily_material_cost_usd")
                ),
                daily_equipment_cost_usd=_opt_float(
                    financials.get("daily_equipment_cost_usd")
                ),
                daily_subcontractor_cost_usd=_opt_float(
                    financials.get("daily_subcontractor_cost_usd")
                ),
                daily_total_cost_usd=daily_total,
                cumulative_spend_to_date_usd=running,
            )
        )
    return points


def compute_budget_variance(
    *,
    contract_value_usd: Optional[float],
    total_spend_to_date_usd: float,
) -> BudgetVariance:
    """Compare spend-to-date against the project's contract value.

    Project.contract_value_usd is the only budget figure this schema
    records — a single total, not a phased or per-stage breakdown, so
    this comparison is necessarily project-wide (docs/NEXT_SPRINT.md,
    Deliverable 2). A project with no contract value set gets
    status="no_budget_set" and null variance figures rather than an
    error or a misleading $0 budget.
    """
    if contract_value_usd is None or contract_value_usd <= 0:
        return BudgetVariance(
            contract_value_usd=contract_value_usd,
            total_spend_to_date_usd=total_spend_to_date_usd,
            budget_remaining_usd=None,
            percent_of_budget_spent=None,
            status="no_budget_set",
        )

    remaining = contract_value_usd - total_spend_to_date_usd
    percent = (total_spend_to_date_usd / contract_value_usd) * 100.0

    if total_spend_to_date_usd > contract_value_usd:
        status = "over_budget"
    elif total_spend_to_date_usd >= contract_value_usd * APPROACHING_BUDGET_THRESHOLD:
        status = "approaching_budget"
    else:
        status = "on_track"

    return BudgetVariance(
        contract_value_usd=contract_value_usd,
        total_spend_to_date_usd=total_spend_to_date_usd,
        budget_remaining_usd=remaining,
        percent_of_budget_spent=round(percent, 2),
        status=status,
    )


def _opt_float(value: object) -> Optional[float]:
    return None if value is None else float(value)
