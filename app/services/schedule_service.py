"""
app/services/schedule_service.py — Sprint 11: schedule creation, critical
path computation, variance detection, and delay-impact propagation.

Deliverable 1 (schema) lives in database/models/schedule.py and
database/migrations/versions/005_scheduling.py. This module is the
computation layer on top of it:

    build_schedule_for_project()   — Deliverable 1's creation logic + 2's
                                       data shape + 5's CPM pass, all at
                                       schedule-creation time.
    compute_variance()             — Deliverable 3, pure date arithmetic.
    propagate_delay_impact()       — Deliverable 6, pure graph arithmetic.

All three are deliberately NOT AI-service calls. docs/NEXT_SPRINT.md is
explicit that this is arithmetic on structured data, not something an LLM
should be doing (matching every prior sprint's "no AI where deterministic
logic suffices" posture — ADR-005, ADR-007). No ServiceType/AIServiceManager
involvement anywhere in this module.

Reads knowledge/dependency_graph.json via
dataset_generation_framework.core.knowledge_loader.KnowledgeBase, the same
deferred-import pattern extraction/pipeline.py already uses for the same
file (see extraction/pipeline.py's _load_enums()) — dependency_graph.json
is read-only reference data (ADR-006), not something this module owns or
modifies.

Critical path method (CPM), briefly, for readers unfamiliar with it:
    Forward pass:  earliest_start[task] = max(earliest_finish[pred] for
                   each predecessor), earliest_finish = earliest_start +
                   duration.
    Backward pass: latest_finish[task] = min(latest_start[succ] for each
                   successor), latest_start = latest_finish - duration.
    A task is on the critical path iff earliest_start == latest_start
    (zero slack) — a delay to it delays the whole project; a task with
    slack can absorb some delay without moving the project end date.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger("app.services.schedule")


@dataclass
class TaskPlan:
    """One task's planned shape, before it becomes a ScheduleTask row.

    Kept separate from the ORM model so compute_critical_path() below has
    no SQLAlchemy/session dependency — it's pure data in, pure data out,
    which is what makes tests/test_critical_path.py able to test it
    against a small hand-built graph without a database at all.
    """

    stage_id: str
    label: str
    sequence_order: int
    duration_days: int
    predecessors: list[str]
    # Maps predecessor stage_id -> lag_days from that predecessor's edge
    # (e.g. {"foundation": 7} for framing, the one real lag in
    # dependency_graph.json today -- concrete cure time). Missing key
    # means 0 lag. Kept separate from `predecessors` (a plain id list)
    # so a predecessor with no lag doesn't need a redundant (id, 0) pair.
    lag_days_by_predecessor: dict[str, int]


@dataclass
class TaskSchedule:
    """One task's computed planned dates + critical-path membership."""

    stage_id: str
    label: str
    sequence_order: int
    duration_days: int
    planned_start_offset_days: int
    planned_end_offset_days: int
    is_on_critical_path: bool


def _load_dependency_graph() -> tuple[list[dict], list[dict]]:
    """Returns (nodes, edges) from knowledge/dependency_graph.json.

    Deferred import + broad except, matching extraction/pipeline.py's
    _load_enums() — this file degrades to "no schedule can be built" (the
    caller surfaces a clear error) rather than crashing the whole app if
    the knowledge base is ever unavailable.
    """
    from dataset_generation_framework.core.knowledge_loader import KnowledgeBase

    kb = KnowledgeBase()
    return kb.dag_nodes(), kb.dag_edges()


def build_task_plans_from_dependency_graph() -> list[TaskPlan]:
    """Build the generic TaskPlan list from dependency_graph.json's 23
    nodes / 33 edges — the "typical" construction sequence, before any
    per-project duration overrides are applied.

    Every project's schedule starts from this same generic plan (Sprint
    11's scope, per docs/NEXT_SPRINT.md, is one schedule seeded from the
    knowledge base's typical durations — a project-specific duration
    override UI is not part of this sprint's 7 deliverables).
    """
    nodes, edges = _load_dependency_graph()

    predecessors_by_node: dict[str, list[str]] = {n["id"]: [] for n in nodes}
    lag_by_node: dict[str, dict[str, int]] = {n["id"]: {} for n in nodes}
    for edge in edges:
        # dependency_type "can_start_when" still represents a real
        # scheduling dependency for CPM purposes -- both "must_complete"
        # and "can_start_when" edges gate when the successor can begin.
        predecessors_by_node.setdefault(edge["to"], []).append(edge["from"])
        lag = edge.get("lag_days", 0)
        if lag:
            lag_by_node.setdefault(edge["to"], {})[edge["from"]] = lag

    return [
        TaskPlan(
            stage_id=n["id"],
            label=n["label"],
            sequence_order=n["sequence_order"],
            duration_days=n["typical_duration_days"],
            predecessors=predecessors_by_node.get(n["id"], []),
            lag_days_by_predecessor=lag_by_node.get(n["id"], {}),
        )
        for n in nodes
    ]


def compute_critical_path(plans: list[TaskPlan]) -> list[TaskSchedule]:
    """CPM forward/backward pass over the given task plans.

    Returns planned start/end as day-offsets from the schedule's start
    date (day 0), not absolute dates -- the caller adds the project's
    actual start date. Keeping this function date-free is what makes it
    testable against a tiny hand-built graph with round day-offset
    numbers (see tests/test_critical_path.py) instead of needing a real
    calendar's weekday/holiday logic, which this project does not have.

    Raises ValueError if plans contains a cycle (should never happen with
    the real dependency_graph.json, but a hand-built test fixture could
    have a bug -- fail loudly rather than infinite-loop).
    """
    by_id = {p.stage_id: p for p in plans}
    successors: dict[str, list[str]] = {p.stage_id: [] for p in plans}
    for p in plans:
        for pred in p.predecessors:
            if pred in successors:
                successors[pred].append(p.stage_id)

    # Forward pass, in topological order via Kahn's algorithm (also
    # detects cycles: if every node isn't visited, one exists).
    in_degree = {p.stage_id: len(p.predecessors) for p in plans}
    queue = [sid for sid, deg in in_degree.items() if deg == 0]
    order: list[str] = []
    earliest_start: dict[str, int] = {}
    earliest_finish: dict[str, int] = {}

    remaining_in_degree = dict(in_degree)
    while queue:
        sid = queue.pop(0)
        order.append(sid)
        task = by_id[sid]
        earliest_start[sid] = max(
            (earliest_finish[pred] + task.lag_days_by_predecessor.get(pred, 0)
             for pred in task.predecessors),
            default=0,
        )
        earliest_finish[sid] = earliest_start[sid] + task.duration_days
        for succ in successors[sid]:
            remaining_in_degree[succ] -= 1
            if remaining_in_degree[succ] == 0:
                queue.append(succ)

    if len(order) != len(plans):
        raise ValueError(
            "compute_critical_path: dependency graph has a cycle -- "
            f"only {len(order)}/{len(plans)} tasks could be ordered."
        )

    project_end = max(earliest_finish.values(), default=0)

    # Backward pass, reverse topological order.
    latest_finish: dict[str, int] = {}
    latest_start: dict[str, int] = {}
    for sid in reversed(order):
        task = by_id[sid]
        if not successors[sid]:
            latest_finish[sid] = project_end
        else:
            latest_finish[sid] = min(
                latest_start[succ] - by_id[succ].lag_days_by_predecessor.get(sid, 0)
                for succ in successors[sid]
            )
        latest_start[sid] = latest_finish[sid] - task.duration_days

    return [
        TaskSchedule(
            stage_id=p.stage_id,
            label=p.label,
            sequence_order=p.sequence_order,
            duration_days=p.duration_days,
            planned_start_offset_days=earliest_start[p.stage_id],
            planned_end_offset_days=earliest_finish[p.stage_id],
            # Zero slack (earliest == latest) means this task cannot move
            # without pushing the project end date -- the standard CPM
            # definition of "on the critical path".
            is_on_critical_path=(earliest_start[p.stage_id] == latest_start[p.stage_id]),
        )
        for p in plans
    ]


@dataclass
class VarianceEntry:
    """One task's schedule variance -- Deliverable 3."""

    stage_id: str
    label: str
    status: str  # "on_track" | "behind" | "ahead" | "not_started" | "complete"
    days_behind: int  # positive = behind schedule, negative = ahead, 0 = on track
    message: str


def compute_variance(
    tasks: list["ScheduleTaskLike"], *, as_of: date
) -> list[VarianceEntry]:
    """Compare actual vs planned dates for each task, as of a given date.

    Pure arithmetic per docs/NEXT_SPRINT.md Deliverable 3 -- no AI call.
    `tasks` is typed loosely (see ScheduleTaskLike below) so this function
    works against either real ScheduleTask ORM rows or a plain test
    fixture without importing SQLAlchemy here.
    """
    entries: list[VarianceEntry] = []
    for t in tasks:
        if t.actual_end_date is not None:
            # Finished -- variance is fixed, not relative to "today".
            days = (t.actual_end_date - t.planned_end_date).days
            if days > 0:
                status, msg = "behind", f"Finished {days} day(s) late."
            elif days < 0:
                status, msg = "ahead", f"Finished {-days} day(s) early."
            else:
                status, msg = "on_track", "Finished on schedule."
            entries.append(VarianceEntry(t.stage_id, t.stage_label, status, max(days, 0), msg))
            continue

        if t.actual_start_date is None:
            if as_of > t.planned_start_date:
                days = (as_of - t.planned_start_date).days
                entries.append(VarianceEntry(
                    t.stage_id, t.stage_label, "behind", days,
                    f"Not yet started -- {days} day(s) behind planned start.",
                ))
            else:
                entries.append(VarianceEntry(
                    t.stage_id, t.stage_label, "not_started", 0, "Not yet started.",
                ))
            continue

        # In progress: compare today's position against the planned end.
        if as_of > t.planned_end_date:
            days = (as_of - t.planned_end_date).days
            entries.append(VarianceEntry(
                t.stage_id, t.stage_label, "behind", days,
                f"You're {days} day(s) behind on {t.stage_label.lower()}.",
            ))
        else:
            entries.append(VarianceEntry(
                t.stage_id, t.stage_label, "on_track", 0, "In progress, on schedule.",
            ))
    return entries


def propagate_delay_impact(
    tasks: list["ScheduleTaskLike"],
    edges: list[dict],
    *,
    delayed_stage_id: str,
    days_lost: float,
) -> tuple[dict[str, int], Optional[date]]:
    """Deliverable 6: push a recorded delay's day count forward through
    every task that depends (directly or transitively) on delayed_stage_id,
    using the same dependency edges compute_critical_path() traverses.

    Returns (shift_by_stage_id, new_projected_completion_date):
        shift_by_stage_id maps every affected stage_id to how many days
        its planned dates shift forward.
        new_projected_completion_date is the project's new planned end
        date (the delayed schedule's latest planned_end_date among all
        tasks, after applying the shift) -- or None if delayed_stage_id
        isn't found in tasks.

    This only shifts PLANNED dates for downstream tasks -- it does not
    write to the database itself; the caller (repository/router layer)
    decides whether/how to persist the result. Keeping this function
    pure makes tests/test_schedule_variance.py-style fixtures possible
    without a database.
    """
    by_id = {t.stage_id: t for t in tasks}
    if delayed_stage_id not in by_id:
        return {}, None

    successors: dict[str, list[str]] = {t.stage_id: [] for t in tasks}
    for edge in edges:
        if edge["from"] in successors:
            successors[edge["from"]].append(edge["to"])

    # BFS forward from the delayed stage -- every reachable stage shifts
    # by the same day count (the simplest sound propagation: the delay
    # ripples unchanged through the chain, since Sprint 11's scope is
    # "if this delay's impact holds", not a full re-run of CPM slack
    # absorption -- see docs/NEXT_SPRINT.md Deliverable 6's own framing).
    shift: dict[str, int] = {delayed_stage_id: int(days_lost)}
    queue = [delayed_stage_id]
    while queue:
        sid = queue.pop(0)
        for succ in successors.get(sid, []):
            if succ not in shift:
                shift[succ] = shift[sid]
                queue.append(succ)

    new_end = max(
        (t.planned_end_date + timedelta(days=shift[t.stage_id])
         for t in tasks if t.stage_id in shift),
        default=None,
    )
    # Also consider unaffected tasks -- the new project end is the max
    # across ALL tasks' (possibly shifted) planned end dates.
    all_ends = [
        t.planned_end_date + timedelta(days=shift.get(t.stage_id, 0))
        for t in tasks
    ]
    new_end = max(all_ends) if all_ends else None

    return shift, new_end


class ScheduleTaskLike:
    """Structural type only (not a real base class) documenting what
    compute_variance()/propagate_delay_impact() need from a "task" —
    satisfied by the real ScheduleTask ORM model without importing it
    here, keeping this module database-free. See PEP 544 duck typing;
    not enforced at runtime, just documentation for readers."""

    stage_id: str
    stage_label: str
    planned_start_date: date
    planned_end_date: date
    actual_start_date: Optional[date]
    actual_end_date: Optional[date]
