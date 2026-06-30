"""
stage_machine.py — DAG-based construction project state machine.

WHY THIS MODULE EXISTS:
    Construction stages follow strict sequencing rules (you cannot paint before drywall,
    you cannot drywall before rough-in inspections). These rules live in
    dependency_graph.json. This module reads the DAG once and provides a clean
    API to simulate a project progressing through stages day by day.

    Without this module, generators would need to hardcode sequencing logic —
    violating the core design principle that knowledge lives only in JSON files.

DESIGN:
    - ProjectState is a pure data class (no logic) capturing all project variables.
    - StageMachine holds the DAG logic derived from knowledge_loader.
    - Generators call machine.advance_day() each simulated day.
    - The machine handles parallel stages (3 rough-in trades run simultaneously),
      lag days (7-day concrete cure before framing), and inspection requirements.

KEY ALGORITHM — can_start():
    For a stage to be startable:
    1. It must not already be active or completed.
    2. All incoming edges must be satisfied:
       - must_complete: predecessor fully complete
       - must_complete_with_inspection: predecessor complete AND inspection passed
       - can_start_when / must_complete_partial: predecessor active OR complete
       - must_pass: predecessor complete AND passed inspection
    3. Special: insulation requires ALL 3 rough-in inspections passed.
    4. Lag days: current_date >= predecessor_completion_date + lag_days.

COMMON BEGINNER MISTAKE:
    Never create a StageMachine() inside a generator loop. It reads the DAG
    at construction time. Create it once, pass it to each project simulation.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from dataset_generation_framework.core.knowledge_loader import KnowledgeBase

logger = logging.getLogger(__name__)


# ── Inspection type mapping ────────────────────────────────────────────────────
# Maps stage_id → the inspection_type that must pass before dependent stages start.
# Derived from the construction knowledge and OSHA sequence requirements.
# This mapping is the only "hardcoded" construction knowledge in Python —
# justified because it is a direct factual mapping between two existing enums
# that doesn't change with scale or configuration.
STAGE_REQUIRES_INSPECTION_BEFORE_NEXT: dict[str, str] = {
    "foundation":          "footing",
    "electrical_rough_in": "rough_electrical",
    "hvac_rough_in":       "rough_hvac",
    "plumbing_rough_in":   "rough_plumbing",
    "insulation":          "insulation",
}

# Stages whose completion requires ALL 3 rough-in inspections (milestone logic)
REQUIRES_ALL_ROUGH_IN_INSPECTIONS = {"insulation"}
ROUGH_IN_STAGES = {"electrical_rough_in", "hvac_rough_in", "plumbing_rough_in"}
ROUGH_IN_INSPECTIONS = {"rough_electrical", "rough_hvac", "rough_plumbing"}


@dataclass
class ProjectState:
    """
    Complete mutable state of one simulated construction project.

    This is a pure data class. All mutation happens through StageMachine methods.
    Generators read from this to build log records.
    """
    # Identity
    project_id: str
    project_name: str
    project_start_date: date
    project_type: str
    project_size_sqft: int
    client_name: str
    foreman_name: str
    contractor_company: str
    permit_number: str
    contract_value_usd: float

    # Stage lifecycle
    completed_stages: set = field(default_factory=set)
    active_stages: set = field(default_factory=set)
    stage_start_dates: dict = field(default_factory=dict)
    stage_completion_dates: dict = field(default_factory=dict)

    # Work remaining per stage (total = work_days + cure_days)
    stage_work_days_remaining: dict = field(default_factory=dict)
    stage_cure_days_remaining: dict = field(default_factory=dict)
    stage_completion_percents: dict = field(default_factory=dict)

    # Inspections that have passed (set of inspection_type strings)
    passed_inspections: set = field(default_factory=set)

    # Aggregate progress
    overall_project_completion_percent: float = 0.0

    # Tracking
    log_count: int = 0
    total_delay_days: float = 0.0

    def is_complete(self) -> bool:
        return "project_closeout" in self.completed_stages

    def is_in_work_phase(self, stage_id: str) -> bool:
        """True if this stage has actual productive work remaining (not curing)."""
        return self.stage_work_days_remaining.get(stage_id, 0) > 0

    def current_stage_percent(self, stage_id: str) -> float:
        return self.stage_completion_percents.get(stage_id, 0.0)


class StageMachine:
    """
    Manages stage transitions for a simulated construction project.
    All sequencing rules derive from knowledge/dependency_graph.json.
    """

    def __init__(self, kb: KnowledgeBase) -> None:
        self.kb = kb
        # Pre-compute stage durations from DAG (authoritative source)
        self._durations: dict[str, int] = {
            node["id"]: node.get("typical_duration_days", 5)
            for node in kb.dag_nodes()
        }
        # Pre-compute lag days from outgoing edges
        self._lag_days: dict[str, int] = {
            node["id"]: kb.max_lag_days_from(node["id"])
            for node in kb.dag_nodes()
        }
        # Topological order for determining "primary" stage
        self._topo_order = kb.topological_order()
        self._topo_rank = {stage: i for i, stage in enumerate(self._topo_order)}

    # ── Stage eligibility ──────────────────────────────────────────────────────

    def can_start(
        self,
        stage_id: str,
        state: ProjectState,
        current_date: date,
    ) -> bool:
        """Return True if stage_id can begin today given the project state."""
        if stage_id in state.completed_stages or stage_id in state.active_stages:
            return False

        edges = self.kb.edges_to(stage_id)

        # Special rule: insulation requires ALL 3 rough-in inspections
        if stage_id in REQUIRES_ALL_ROUGH_IN_INSPECTIONS:
            if not ROUGH_IN_STAGES.issubset(state.completed_stages):
                return False
            if not ROUGH_IN_INSPECTIONS.issubset(state.passed_inspections):
                return False

        for edge in edges:
            from_stage = edge["from"]
            dep_type = edge["dependency_type"]

            if dep_type in ("must_complete", "must_pass"):
                if from_stage not in state.completed_stages:
                    return False
                # Check lag days
                completion = state.stage_completion_dates.get(from_stage)
                lag = edge.get("lag_days", 0)
                if completion and lag > 0:
                    if current_date < completion + timedelta(days=lag):
                        return False
                # must_pass also requires inspection
                if dep_type == "must_pass":
                    insp = STAGE_REQUIRES_INSPECTION_BEFORE_NEXT.get(from_stage)
                    if insp and insp not in state.passed_inspections:
                        return False

            elif dep_type == "must_complete_with_inspection":
                if from_stage not in state.completed_stages:
                    return False
                insp = STAGE_REQUIRES_INSPECTION_BEFORE_NEXT.get(from_stage)
                if insp and insp not in state.passed_inspections:
                    return False

            elif dep_type in ("can_start_when", "must_complete_partial"):
                # Predecessor must be active OR complete
                if (from_stage not in state.completed_stages
                        and from_stage not in state.active_stages):
                    return False

        return True

    def available_stages(
        self,
        state: ProjectState,
        current_date: date,
    ) -> list[str]:
        """Return all stages that can start today, in topological order."""
        return [
            s for s in self._topo_order
            if self.can_start(s, state, current_date)
        ]

    # ── Stage lifecycle ────────────────────────────────────────────────────────

    def start_stage(
        self,
        stage_id: str,
        state: ProjectState,
        current_date: date,
        rng: random.Random,
        variance: tuple[float, float],
    ) -> None:
        """
        Activate a stage. Milestones complete instantly.
        Work stages get a duration sampled within variance range.
        """
        if self.kb.is_milestone(stage_id):
            # Milestones complete on the day they become available
            state.completed_stages.add(stage_id)
            state.stage_completion_dates[stage_id] = current_date
            state.stage_completion_percents[stage_id] = 100.0
            logger.debug("Milestone %s achieved on %s", stage_id, current_date)
            return

        base_days = self._durations.get(stage_id, 5)
        factor = rng.uniform(*variance)
        work_days = max(1, round(base_days * factor))
        cure_days = self._lag_days.get(stage_id, 0)

        state.active_stages.add(stage_id)
        state.stage_start_dates[stage_id] = current_date
        state.stage_work_days_remaining[stage_id] = float(work_days)
        state.stage_cure_days_remaining[stage_id] = float(cure_days)
        state.stage_completion_percents[stage_id] = 0.0

        logger.debug(
            "Started %s on %s (work=%d days, cure=%d days)",
            stage_id, current_date, work_days, cure_days,
        )

    def advance_day(
        self,
        state: ProjectState,
        productivity: float,
        current_date: date,
        rng: random.Random,
    ) -> list[str]:
        """
        Advance all active stages by one day of work.

        productivity: 0.0 (no work) → 1.0 (full productivity)
        Returns list of stage_ids that completed today.

        Work days consume at rate = productivity (1 day = full speed).
        Cure days consume at rate = 1.0/day regardless of productivity
        (concrete cures on its own schedule regardless of workers).
        """
        completed_today: list[str] = []

        for stage_id in list(state.active_stages):
            if self.kb.is_milestone(stage_id):
                # Should have been handled in start_stage; clean up
                state.active_stages.discard(stage_id)
                state.completed_stages.add(stage_id)
                completed_today.append(stage_id)
                continue

            work_rem = state.stage_work_days_remaining.get(stage_id, 0.0)
            cure_rem = state.stage_cure_days_remaining.get(stage_id, 0.0)

            if work_rem > 0:
                work_rem = max(0.0, work_rem - productivity)
                state.stage_work_days_remaining[stage_id] = work_rem
            elif cure_rem > 0:
                # Curing phase — advances one day regardless of workers
                cure_rem = max(0.0, cure_rem - 1.0)
                state.stage_cure_days_remaining[stage_id] = cure_rem

            # Update completion percent
            base_work = self._durations.get(stage_id, 5)
            work_done = base_work - max(work_rem, 0)
            pct = min(99.9, (work_done / base_work) * 100.0) if base_work > 0 else 100.0

            if work_rem <= 0 and cure_rem <= 0:
                pct = 100.0
                state.active_stages.discard(stage_id)
                state.completed_stages.add(stage_id)
                state.stage_completion_dates[stage_id] = current_date
                completed_today.append(stage_id)
                logger.debug("Completed %s on %s", stage_id, current_date)

            state.stage_completion_percents[stage_id] = round(pct, 1)

        return completed_today

    # ── Stage information ──────────────────────────────────────────────────────

    def primary_stage(self, state: ProjectState) -> str:
        """
        Return the most significant stage for today's log record.

        Picks the most advanced (highest topological rank) active non-milestone stage.
        Falls back to the most recently completed stage if nothing is active.
        """
        active_non_milestones = [
            s for s in state.active_stages
            if not self.kb.is_milestone(s)
        ]
        if active_non_milestones:
            # Most advanced stage by topological rank
            return max(
                active_non_milestones,
                key=lambda s: self._topo_rank.get(s, 0),
            )

        if state.completed_stages:
            completed_non_milestones = [
                s for s in state.completed_stages
                if not self.kb.is_milestone(s)
            ]
            if completed_non_milestones:
                return max(
                    completed_non_milestones,
                    key=lambda s: self._topo_rank.get(s, 0),
                )

        return "site_preparation"

    def all_active_stages_for_log(self, state: ProjectState) -> list[str]:
        """All non-milestone active stage IDs sorted by topological order."""
        return sorted(
            [s for s in state.active_stages if not self.kb.is_milestone(s)],
            key=lambda s: self._topo_rank.get(s, 0),
        )

    def compute_overall_completion(self, state: ProjectState) -> float:
        """
        Estimate overall project completion as weighted average across all
        non-milestone, non-optional stages in the topological order.
        """
        all_stages = [
            n["id"] for n in self.kb.dag_nodes()
            if n.get("type") != "milestone" and not n.get("is_optional", False)
        ]
        if not all_stages:
            return 0.0

        total_pct = 0.0
        for stage in all_stages:
            if stage in state.completed_stages:
                total_pct += 100.0
            else:
                total_pct += state.stage_completion_percents.get(stage, 0.0)

        return round(total_pct / len(all_stages), 1)

    def record_inspection_pass(
        self,
        stage_id: str,
        state: ProjectState,
        inspection_type: str,
    ) -> None:
        """Record that an inspection passed. Unlocks dependent stages."""
        state.passed_inspections.add(inspection_type)
        logger.debug(
            "Inspection '%s' passed for stage %s", inspection_type, stage_id
        )
