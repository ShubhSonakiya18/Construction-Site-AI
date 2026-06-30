"""
rule_engine.py — Applies construction_rules.json for sequence and parallel validation.

WHY THIS MODULE EXISTS:
    construction_rules.json contains 38 domain rules with rich semantics:
    sequential dependencies, parallel allowances, material-stage constraints,
    worker constraints, and weather rules. Rather than duplicating this logic
    in each generator, the RuleEngine provides a single query API.

    Generators ask: "Can I start roofing while framing is active?"
    RuleEngine answers using the JSON, not hardcoded Python ifs.

RULE TYPES HANDLED:
    - sequential    → stage A must precede stage B (with optional lag_days)
    - parallel      → stages that can run simultaneously
    - material      → which materials are valid for which stages
    - worker        → trade-stage matching
    - safety        → incident-status rules
    - weather       → weather-work constraints
    - quantity      → numeric sanity bounds

BEGINNER MISTAKE TO AVOID:
    Don't call RuleEngine() on every generated record. Instantiate once and
    reuse. The rules are loaded once at construction time.
"""
from __future__ import annotations

import logging
from typing import Optional

from dataset_generation_framework.core.knowledge_loader import KnowledgeBase

logger = logging.getLogger(__name__)


class RuleEngine:
    """
    Query interface for construction_rules.json.

    All methods accept stage_ids and return answers derived from the JSON,
    never from hardcoded Python logic.
    """

    def __init__(self, kb: KnowledgeBase) -> None:
        self.kb = kb
        self._rules = kb.all_construction_rules()
        self._seq_rules = kb.construction_rules_by_type("sequential")
        self._par_rules = kb.construction_rules_by_type("parallel")
        self._mat_rules = kb.construction_rules_by_type("material")
        self._wrk_rules = kb.construction_rules_by_type("worker")
        self._saf_rules = kb.construction_rules_by_type("safety")
        self._wth_rules = kb.construction_rules_by_type("weather")
        self._qty_rules = kb.construction_rules_by_type("quantity")

        # Precompute parallel stage sets from parallel rules
        self._parallel_sets: list[set[str]] = []
        for rule in self._par_rules:
            stages = rule.get("stages_in_parallel") or rule.get("parallel_stages") or []
            if stages:
                self._parallel_sets.append(set(stages))

        # Also add parallel groups from dependency graph
        for pg in kb.parallel_groups():
            stages = pg.get("stages", [])
            if stages:
                self._parallel_sets.append(set(stages))

    # ── Sequential Rules ───────────────────────────────────────────────────────

    def lag_days_between(self, from_stage: str, to_stage: str) -> int:
        """Return lag_days required between from_stage completion and to_stage start."""
        for rule in self._seq_rules:
            if (rule.get("prerequisite_stage") == from_stage
                    and rule.get("dependent_stage") == to_stage):
                return rule.get("lag_days", 0)
        # Also check dependency graph edges as fallback
        for edge in self.kb.edges_from(from_stage):
            if edge["to"] == to_stage:
                return edge.get("lag_days", 0)
        return 0

    def is_valid_sequence(self, completed: set[str], current_stage: str) -> tuple[bool, Optional[str]]:
        """
        Check whether current_stage is valid given completed stages.
        Returns (is_valid, error_message_or_None).
        """
        for rule in self._seq_rules:
            dep = rule.get("dependent_stage")
            prereq = rule.get("prerequisite_stage")
            sev = rule.get("severity", "warning")

            if dep != current_stage:
                continue
            if prereq and prereq not in completed:
                msg = rule.get("validation_message") or f"{dep} requires {prereq} to be complete first"
                return False, f"[{rule['rule_id']}:{sev}] {msg}"

        return True, None

    # ── Parallel Rules ─────────────────────────────────────────────────────────

    def can_run_parallel(self, stage_a: str, stage_b: str) -> bool:
        """Return True if stage_a and stage_b may be active simultaneously."""
        for par_set in self._parallel_sets:
            if stage_a in par_set and stage_b in par_set:
                return True
        return False

    def parallel_peers(self, stage_id: str) -> list[str]:
        """Return all stages that may run in parallel with stage_id."""
        peers: set[str] = set()
        for par_set in self._parallel_sets:
            if stage_id in par_set:
                peers.update(par_set - {stage_id})
        return sorted(peers)

    # ── Material Rules ─────────────────────────────────────────────────────────

    def expected_material_categories(self, stage_id: str) -> list[str]:
        """Return material categories typically used in a stage (from knowledge stages)."""
        materials = self.kb.stage_materials(stage_id)
        categories = list({m.get("category", "other") for m in materials})
        # Also include from ontology materials
        for m in self.kb.materials_for_stage(stage_id):
            cat = m.get("category", "other")
            if cat not in categories:
                categories.append(cat)
        return categories

    def is_material_expected_for_stage(self, material_category: str, stage_id: str) -> bool:
        """Return True if this material category is normal for this stage."""
        return material_category in self.expected_material_categories(stage_id)

    # ── Worker Rules ───────────────────────────────────────────────────────────

    def expected_trades_for_stage(self, stage_id: str) -> list[str]:
        """Trade IDs (schema enum values) that typically work on this stage."""
        trades = self.kb.trades_active_in_stage(stage_id)
        # Map ontology trade IDs to schema trade enum values
        trade_id_to_enum = {
            "trade_general_labor":    "general_labor",
            "trade_concrete":         "concrete",
            "trade_framing":          "framing_carpenter",
            "trade_electrician":      "electrician",
            "trade_plumber":          "plumber",
            "trade_hvac":             "hvac_technician",
            "trade_roofer":           "roofer",
            "trade_drywall":          "drywall",
            "trade_painter":          "painter",
            "trade_flooring":         "flooring_installer",
            "trade_tile":             "tile_setter",
            "trade_cabinet":          "cabinet_installer",
            "trade_trim":             "finish_carpenter",
            "trade_insulation":       "insulation_installer",
        }
        result = []
        for trade in trades:
            enum_val = trade_id_to_enum.get(trade["id"])
            if enum_val:
                result.append(enum_val)
        # Always include general_labor and site_supervisor
        if "general_labor" not in result:
            result.append("general_labor")
        return result

    def typical_worker_count_range(self, stage_id: str) -> tuple[int, int]:
        """Return (min, max) worker count typical for a stage."""
        workers = self.kb.stage_workers(stage_id)
        total_min, total_max = 0, 0
        for w in workers:
            count_str = str(w.get("typical_count", "1"))
            if "-" in count_str:
                lo, hi = count_str.split("-")
                total_min += int(lo.strip())
                total_max += int(hi.strip())
            else:
                val = int(count_str.strip().split()[0])
                total_min += val
                total_max += val

        if total_min == 0 and total_max == 0:
            # Fallback: use ontology trade count
            trade_count = len(self.kb.trades_active_in_stage(stage_id))
            total_min = max(1, trade_count * 1)
            total_max = max(3, trade_count * 3)

        return max(1, total_min), max(total_min + 1, total_max)

    # ── Weather Rules ──────────────────────────────────────────────────────────

    def stage_is_weather_sensitive(self, stage_id: str) -> bool:
        """Return True if this stage is affected by rain/weather."""
        sensitivity = self.kb.stage_weather_sensitivity(stage_id)
        return sensitivity in ("high", "medium")

    def weather_stops_work_on_stage(self, weather_condition: str, stage_id: str) -> bool:
        """Return True if this weather condition halts work on this stage."""
        from dataset_generation_framework.config import WORK_STOPPING_CONDITIONS, WEATHER_SENSITIVE_OUTDOOR_STAGES
        if weather_condition not in WORK_STOPPING_CONDITIONS:
            return False
        return stage_id in WEATHER_SENSITIVE_OUTDOOR_STAGES

    # ── Severity helpers ───────────────────────────────────────────────────────

    def fatal_rules(self) -> list[dict]:
        return [r for r in self._seq_rules if r.get("severity") == "fatal"]

    def error_rules(self) -> list[dict]:
        return [r for r in self._rules if r.get("severity") == "error"]
