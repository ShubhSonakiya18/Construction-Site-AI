"""
tests/test_critical_path.py — Sprint 11 Deliverable 5/7: CPM forward/
backward pass correctness against small, hand-verifiable dependency
graphs — not the full 23-node real one, per docs/NEXT_SPRINT.md's own
guidance, so every expected answer here is checkable by hand.

Also covers compute_variance() (Deliverable 3) and propagate_delay_impact()
(Deliverable 6), which are pure functions over plain fixtures — no
database, no app fixtures needed for any test in this file.
"""
from __future__ import annotations

from datetime import date

from app.services.schedule_service import (
    ScheduleTaskLike,
    TaskPlan,
    compute_critical_path,
    compute_variance,
    propagate_delay_impact,
)


class FakeTask:
    """A minimal stand-in satisfying ScheduleTaskLike, for
    compute_variance()/propagate_delay_impact() tests below — no ORM,
    no session."""

    def __init__(
        self, stage_id, stage_label, planned_start_date, planned_end_date,
        actual_start_date=None, actual_end_date=None,
    ):
        self.stage_id = stage_id
        self.stage_label = stage_label
        self.planned_start_date = planned_start_date
        self.planned_end_date = planned_end_date
        self.actual_start_date = actual_start_date
        self.actual_end_date = actual_end_date


# ── compute_critical_path() ─────────────────────────────────────────────────

class TestComputeCriticalPathLinearChain:
    """A -> B -> C, no branching. The entire chain must be critical —
    there is no alternate path to have slack against."""

    def _plans(self):
        return [
            TaskPlan("a", "A", 0, 5, [], {}),
            TaskPlan("b", "B", 1, 3, ["a"], {}),
            TaskPlan("c", "C", 2, 2, ["b"], {}),
        ]

    def test_all_three_tasks_on_critical_path(self):
        result = {r.stage_id: r for r in compute_critical_path(self._plans())}
        assert result["a"].is_on_critical_path
        assert result["b"].is_on_critical_path
        assert result["c"].is_on_critical_path

    def test_planned_offsets_are_sequential(self):
        result = {r.stage_id: r for r in compute_critical_path(self._plans())}
        assert result["a"].planned_start_offset_days == 0
        assert result["a"].planned_end_offset_days == 5
        assert result["b"].planned_start_offset_days == 5
        assert result["b"].planned_end_offset_days == 8
        assert result["c"].planned_start_offset_days == 8
        assert result["c"].planned_end_offset_days == 10


class TestComputeCriticalPathDiamond:
    """A -> {B, C} -> D. B is 10 days, C is 2 days — both feed D, so B
    (the longer branch) is critical and C has 8 days of slack."""

    def _plans(self):
        return [
            TaskPlan("a", "A", 0, 2, [], {}),
            TaskPlan("b", "B", 1, 10, ["a"], {}),
            TaskPlan("c", "C", 1, 2, ["a"], {}),
            TaskPlan("d", "D", 2, 3, ["b", "c"], {}),
        ]

    def test_longer_branch_is_critical(self):
        result = {r.stage_id: r for r in compute_critical_path(self._plans())}
        assert result["b"].is_on_critical_path
        assert not result["c"].is_on_critical_path

    def test_shared_endpoints_are_critical(self):
        result = {r.stage_id: r for r in compute_critical_path(self._plans())}
        assert result["a"].is_on_critical_path
        assert result["d"].is_on_critical_path

    def test_project_end_is_max_of_both_branches(self):
        result = {r.stage_id: r for r in compute_critical_path(self._plans())}
        # A(2) + B(10) + D(3) = 15, vs A(2) + C(2) + D(3) = 7 -- the
        # longer branch determines D's earliest start.
        assert result["d"].planned_end_offset_days == 15


class TestComputeCriticalPathWithLag:
    """A -> B with a 7-day lag on the edge (mirrors the real
    foundation->framing concrete-cure lag in dependency_graph.json).
    The lag must add to B's start without being any task's duration."""

    def _plans(self):
        return [
            TaskPlan("a", "A", 0, 5, [], {}),
            TaskPlan("b", "B", 1, 3, ["a"], {"a": 7}),
        ]

    def test_lag_pushes_successor_start(self):
        result = {r.stage_id: r for r in compute_critical_path(self._plans())}
        # A finishes at offset 5; +7 lag -> B starts at 12, ends at 15.
        assert result["b"].planned_start_offset_days == 12
        assert result["b"].planned_end_offset_days == 15

    def test_both_tasks_still_critical(self):
        result = {r.stage_id: r for r in compute_critical_path(self._plans())}
        assert result["a"].is_on_critical_path
        assert result["b"].is_on_critical_path


class TestComputeCriticalPathCycleDetection:
    def test_raises_value_error_on_cycle(self):
        plans = [
            TaskPlan("a", "A", 0, 1, ["b"], {}),
            TaskPlan("b", "B", 1, 1, ["a"], {}),
        ]
        try:
            compute_critical_path(plans)
            assert False, "expected ValueError for a cyclic graph"
        except ValueError:
            pass


class TestComputeCriticalPathAgainstRealKnowledgeFile:
    """One integration-style check against the real
    knowledge/dependency_graph.json -- confirms the loader + CPM pass
    together produce a sane, non-empty result on the actual 23-node
    graph, without hardcoding its exact numbers here (that's ADR-049's
    job to explain, not this test's)."""

    def test_real_graph_produces_23_tasks_with_at_least_one_critical(self):
        from app.services.schedule_service import build_task_plans_from_dependency_graph

        plans = build_task_plans_from_dependency_graph()
        assert len(plans) == 23
        result = compute_critical_path(plans)
        assert len(result) == 23
        assert any(r.is_on_critical_path for r in result)
        # Every planned_end_offset_days must be >= that task's own
        # duration (sanity: nothing finishes before it could possibly
        # have started).
        for r in result:
            assert r.planned_end_offset_days - r.planned_start_offset_days == r.duration_days


# ── compute_variance() ──────────────────────────────────────────────────────

class TestComputeVariance:
    def test_not_started_and_not_yet_due_is_not_started(self):
        task = FakeTask("a", "A", date(2026, 6, 1), date(2026, 6, 10))
        result = compute_variance([task], as_of=date(2026, 5, 1))
        assert result[0].status == "not_started"
        assert result[0].days_behind == 0

    def test_not_started_and_overdue_is_behind(self):
        task = FakeTask("a", "A", date(2026, 6, 1), date(2026, 6, 10))
        result = compute_variance([task], as_of=date(2026, 6, 6))
        assert result[0].status == "behind"
        assert result[0].days_behind == 5

    def test_in_progress_within_planned_window_is_on_track(self):
        task = FakeTask(
            "a", "A", date(2026, 6, 1), date(2026, 6, 10),
            actual_start_date=date(2026, 6, 1),
        )
        result = compute_variance([task], as_of=date(2026, 6, 5))
        assert result[0].status == "on_track"

    def test_in_progress_past_planned_end_is_behind(self):
        task = FakeTask(
            "a", "A", date(2026, 6, 1), date(2026, 6, 10),
            actual_start_date=date(2026, 6, 1),
        )
        result = compute_variance([task], as_of=date(2026, 6, 15))
        assert result[0].status == "behind"
        assert result[0].days_behind == 5

    def test_finished_late_reports_days_late(self):
        task = FakeTask(
            "a", "A", date(2026, 6, 1), date(2026, 6, 10),
            actual_start_date=date(2026, 6, 1), actual_end_date=date(2026, 6, 13),
        )
        result = compute_variance([task], as_of=date(2026, 7, 1))
        assert result[0].status == "behind"
        assert result[0].days_behind == 3

    def test_finished_early_reports_ahead(self):
        task = FakeTask(
            "a", "A", date(2026, 6, 1), date(2026, 6, 10),
            actual_start_date=date(2026, 6, 1), actual_end_date=date(2026, 6, 8),
        )
        result = compute_variance([task], as_of=date(2026, 7, 1))
        assert result[0].status == "ahead"

    def test_message_names_the_stage_for_behind_in_progress_tasks(self):
        task = FakeTask(
            "framing", "Framing", date(2026, 6, 1), date(2026, 6, 10),
            actual_start_date=date(2026, 6, 1),
        )
        result = compute_variance([task], as_of=date(2026, 6, 15))
        assert "framing" in result[0].message.lower()
        assert "5 day" in result[0].message


# ── propagate_delay_impact() ─────────────────────────────────────────────────

class TestPropagateDelayImpact:
    def _tasks_and_edges(self):
        tasks = [
            FakeTask("a", "A", date(2026, 1, 1), date(2026, 1, 5)),
            FakeTask("b", "B", date(2026, 1, 5), date(2026, 1, 10)),
            FakeTask("c", "C", date(2026, 1, 10), date(2026, 1, 15)),
            # d is a sibling of b/c, not downstream of a's delay.
            FakeTask("d", "D", date(2026, 1, 1), date(2026, 1, 3)),
        ]
        edges = [
            {"from": "a", "to": "b"},
            {"from": "b", "to": "c"},
        ]
        return tasks, edges

    def test_delay_propagates_through_the_chain(self):
        tasks, edges = self._tasks_and_edges()
        shift, new_end = propagate_delay_impact(
            tasks, edges, delayed_stage_id="a", days_lost=3,
        )
        assert shift["a"] == 3
        assert shift["b"] == 3
        assert shift["c"] == 3

    def test_unrelated_sibling_is_unaffected(self):
        tasks, edges = self._tasks_and_edges()
        shift, _ = propagate_delay_impact(
            tasks, edges, delayed_stage_id="a", days_lost=3,
        )
        assert "d" not in shift

    def test_new_projected_completion_reflects_the_shift(self):
        tasks, edges = self._tasks_and_edges()
        _, new_end = propagate_delay_impact(
            tasks, edges, delayed_stage_id="a", days_lost=3,
        )
        # c's planned_end_date (Jan 15) shifts by 3 -> Jan 18, which
        # becomes the new project end (later than d's unaffected Jan 3).
        assert new_end == date(2026, 1, 18)

    def test_unknown_stage_id_returns_empty(self):
        tasks, edges = self._tasks_and_edges()
        shift, new_end = propagate_delay_impact(
            tasks, edges, delayed_stage_id="nonexistent", days_lost=3,
        )
        assert shift == {}
        assert new_end is None
