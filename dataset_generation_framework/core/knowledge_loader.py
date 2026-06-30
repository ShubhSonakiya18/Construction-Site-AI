"""
knowledge_loader.py — Loads all 6 Sprint 1 knowledge JSON files exactly once.

WHY THIS MODULE EXISTS:
    Every generator, validator, and rule engine needs access to construction domain
    knowledge. Without a central loader, each module would independently open files,
    re-parse JSON, and hold its own copy — wasting memory and creating drift risk.
    This module provides a single KnowledgeBase instance (singleton) shared across
    the entire framework. Files are loaded once at startup; all access is in-memory.

WHY SINGLETON:
    For a 500k-record generation run, thousands of calls to trades_active_in_stage()
    will happen. Without caching, each call would require a list scan. With a singleton,
    the scan happens over the same in-memory list every time.

WHY NOT A DATABASE:
    See ADR-006: Knowledge is read-only at runtime. JSON files give version control,
    no connection management, and are natively AI-readable for future RAG integration.

BEGINNER MISTAKE TO AVOID:
    Do NOT import KnowledgeBase and call KnowledgeBase() directly in every module.
    Use get_knowledge_base() to get the shared instance.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from dataset_generation_framework.config import KNOWLEDGE_FILES

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """
    Unified access layer for all 6 Sprint 1 knowledge base JSON files.

    Public API is organized by domain:
        - schema()           → ConstructionDailyLog schema
        - stages API         → construction_stages.json
        - dag API            → dependency_graph.json
        - rules API          → construction_rules.json
        - validation API     → validation_rules.json
        - ontology API       → construction_ontology.json
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._load_all()
        self._build_indexes()

    # ── Loading ────────────────────────────────────────────────────────────────

    def _load_all(self) -> None:
        for key, path in KNOWLEDGE_FILES.items():
            if not Path(path).exists():
                raise FileNotFoundError(
                    f"Knowledge file missing: {path}\n"
                    f"Sprint 1 must be complete before running Sprint 2."
                )
            with open(path, "r", encoding="utf-8") as f:
                self._data[key] = json.load(f)
            logger.debug("Loaded: %s", Path(path).name)
        logger.info(
            "KnowledgeBase loaded %d files successfully.", len(self._data)
        )

    def _build_indexes(self) -> None:
        """Pre-build lookup indexes for O(1) access patterns."""
        # Stage ID → stage dict
        self._stage_index: dict[str, dict] = {
            s["id"]: s for s in self._data["stages"].get("stages", [])
        }
        # DAG node ID → node dict
        self._dag_node_index: dict[str, dict] = {
            n["id"]: n for n in self._data["dependency_graph"]["nodes"]
        }
        # Validation rule ID → rule dict
        self._val_rule_index: dict[str, dict] = {
            r["rule_id"]: r for r in self._data["validation_rules"]["rules"]
        }
        # Construction rule ID → rule dict
        self._const_rule_index: dict[str, dict] = {
            r["rule_id"]: r for r in self._data["construction_rules"].get("rules", [])
        }
        # stage_id → list of incoming edges
        self._edges_to: dict[str, list[dict]] = {}
        # stage_id → list of outgoing edges
        self._edges_from: dict[str, list[dict]] = {}
        for edge in self._data["dependency_graph"]["edges"]:
            self._edges_to.setdefault(edge["to"], []).append(edge)
            self._edges_from.setdefault(edge["from"], []).append(edge)

    # ── Schema API ─────────────────────────────────────────────────────────────

    @property
    def raw_schema(self) -> dict:
        return self._data["schema"]

    def stage_enum(self) -> list[str]:
        """22-value current_stage enum from the JSON Schema."""
        return self._data["schema"]["properties"]["current_stage"]["enum"]

    def trade_enum(self) -> list[str]:
        """Trade enum from schema definitions."""
        return self._data["schema"]["definitions"]["trade_enum"]["enum"]

    def weather_condition_enum(self) -> list[str]:
        props = self._data["schema"]["properties"]
        return [
            v for v in
            props["weather"]["properties"]["morning_condition"]["enum"]
            if v is not None
        ]

    # ── Construction Stages API ────────────────────────────────────────────────

    def all_knowledge_stages(self) -> list[dict]:
        """All stages from construction_stages.json."""
        return self._data["stages"].get("stages", [])

    def knowledge_stage(self, stage_id: str) -> Optional[dict]:
        """Stage dict from construction_stages.json, or None if not found."""
        return self._stage_index.get(stage_id)

    def stage_materials(self, stage_id: str) -> list[dict]:
        """Materials list from construction_stages.json for a given stage."""
        stage = self._stage_index.get(stage_id)
        return stage.get("materials", []) if stage else []

    def stage_workers(self, stage_id: str) -> list[dict]:
        """Workers list from construction_stages.json for a given stage."""
        stage = self._stage_index.get(stage_id)
        return stage.get("workers", []) if stage else []

    def stage_hazards(self, stage_id: str) -> list[dict]:
        """Safety hazards from construction_stages.json for a given stage."""
        stage = self._stage_index.get(stage_id)
        return stage.get("safety_hazards", []) if stage else []

    def stage_weather_sensitivity(self, stage_id: str) -> str:
        """Weather sensitivity level ('high', 'medium', 'low') for a stage."""
        stage = self._stage_index.get(stage_id)
        return stage.get("weather_sensitivity", "low") if stage else "low"

    def stage_inspection_points(self, stage_id: str) -> list[dict]:
        """Required inspection points for a stage."""
        stage = self._stage_index.get(stage_id)
        return stage.get("inspection_points", []) if stage else []

    def stage_common_delays(self, stage_id: str) -> list[dict]:
        """Common delay types for a stage."""
        stage = self._stage_index.get(stage_id)
        return stage.get("common_delays", []) if stage else []

    # ── Dependency Graph (DAG) API ─────────────────────────────────────────────

    def dag_nodes(self) -> list[dict]:
        return self._data["dependency_graph"]["nodes"]

    def dag_edges(self) -> list[dict]:
        return self._data["dependency_graph"]["edges"]

    def dag_node(self, stage_id: str) -> Optional[dict]:
        return self._dag_node_index.get(stage_id)

    def topological_order(self) -> list[str]:
        """Valid execution order from the dependency graph."""
        return self._data["dependency_graph"]["topological_sort"]["order"]

    def critical_path_nodes(self) -> list[str]:
        return self._data["dependency_graph"]["critical_path"]["path_nodes_in_order"]

    def parallel_groups(self) -> list[dict]:
        return self._data["dependency_graph"]["parallel_groups"]

    def is_milestone(self, stage_id: str) -> bool:
        node = self._dag_node_index.get(stage_id)
        return node.get("type") == "milestone" if node else False

    def is_optional_stage(self, stage_id: str) -> bool:
        node = self._dag_node_index.get(stage_id)
        return node.get("is_optional", False) if node else False

    def stage_typical_duration_days(self, stage_id: str) -> int:
        """Canonical stage duration from the dependency graph."""
        node = self._dag_node_index.get(stage_id)
        return node.get("typical_duration_days", 5) if node else 5

    def edges_to(self, stage_id: str) -> list[dict]:
        """All edges whose 'to' is stage_id (incoming dependencies)."""
        return self._edges_to.get(stage_id, [])

    def edges_from(self, stage_id: str) -> list[dict]:
        """All edges whose 'from' is stage_id (what this stage unlocks)."""
        return self._edges_from.get(stage_id, [])

    def max_lag_days_from(self, stage_id: str) -> int:
        """Max lag_days across all outgoing edges (cure time / wait after completion)."""
        return max(
            (e.get("lag_days", 0) for e in self.edges_from(stage_id)),
            default=0,
        )

    # ── Construction Rules API ─────────────────────────────────────────────────

    def all_construction_rules(self) -> list[dict]:
        return self._data["construction_rules"].get("rules", [])

    def construction_rules_by_type(self, rule_type: str) -> list[dict]:
        return [r for r in self.all_construction_rules() if r.get("rule_type") == rule_type]

    def construction_rules_for_stage(self, stage_id: str) -> list[dict]:
        """Rules where stage_id appears as prerequisite or dependent."""
        index = self._data["construction_rules"].get("rule_index", {}).get("by_stage", {})
        rule_ids = index.get(stage_id, [])
        return [self._const_rule_index[rid] for rid in rule_ids if rid in self._const_rule_index]

    # ── Validation Rules API ───────────────────────────────────────────────────

    def all_validation_rules(self) -> list[dict]:
        return self._data["validation_rules"]["rules"]

    def validation_rule(self, rule_id: str) -> Optional[dict]:
        return self._val_rule_index.get(rule_id)

    def _phase_rule_ids(self, phase_key: str) -> list[str]:
        return self._data["validation_rules"]["rule_execution_order"].get(phase_key, [])

    def blocking_rule_ids(self) -> list[str]:
        return self._phase_rule_ids("phase_1_blocking")

    def non_blocking_rule_ids(self) -> list[str]:
        return self._phase_rule_ids("phase_2_errors")

    def warning_rule_ids(self) -> list[str]:
        return self._phase_rule_ids("phase_3_warnings")

    def info_rule_ids(self) -> list[str]:
        return self._phase_rule_ids("phase_4_info")

    # ── Ontology API ───────────────────────────────────────────────────────────

    def ontology_trades(self) -> list[dict]:
        return self._data["ontology"]["entities"]["trades"]

    def ontology_materials(self) -> list[dict]:
        return self._data["ontology"]["entities"]["materials"]

    def ontology_hazards(self) -> list[dict]:
        return self._data["ontology"]["entities"]["safety_hazards"]

    def ontology_ppe_types(self) -> list[dict]:
        return self._data["ontology"]["entities"]["ppe_types"]

    def ontology_delay_types(self) -> list[dict]:
        return self._data["ontology"]["entities"]["delay_types"]

    def ontology_inspection_types(self) -> list[dict]:
        return self._data["ontology"]["entities"]["inspection_types"]

    def ontology_weather_conditions(self) -> list[dict]:
        return self._data["ontology"]["entities"].get("weather_conditions", [])

    def trades_active_in_stage(self, stage_id: str) -> list[dict]:
        """All trade entities active during a given stage (from ontology)."""
        return [
            t for t in self.ontology_trades()
            if stage_id in t.get("active_in_stages", [])
        ]

    def materials_for_stage(self, stage_id: str) -> list[dict]:
        """All material entities used in a given stage (from ontology)."""
        return [
            m for m in self.ontology_materials()
            if stage_id in m.get("used_in_stages", [])
        ]

    def hazards_for_stage(self, stage_id: str) -> list[dict]:
        """All safety hazards associated with a given stage (from ontology)."""
        return [
            h for h in self.ontology_hazards()
            if stage_id in h.get("active_in_stages", [])
        ]

    def ppe_for_stage(self, stage_id: str) -> list[str]:
        """PPE type IDs required for a stage (from ontology relationships)."""
        ppe_ids = set()
        relationships = self._data["ontology"].get("relationships", [])
        hazards_in_stage = {h["id"] for h in self.hazards_for_stage(stage_id)}
        for rel in relationships:
            if rel.get("predicate") == "MITIGATED_BY" and rel.get("subject") in hazards_in_stage:
                ppe_ids.add(rel["object"])
        return list(ppe_ids)


# ── Module-level singleton ─────────────────────────────────────────────────────
# Use get_knowledge_base() instead of KnowledgeBase() directly.
# This ensures the 6 JSON files are read exactly once per process.

_kb_instance: Optional[KnowledgeBase] = None


def get_knowledge_base() -> KnowledgeBase:
    """Return the shared KnowledgeBase singleton. Thread-safe for read access."""
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = KnowledgeBase()
    return _kb_instance


def reset_knowledge_base() -> None:
    """Force a reload of all knowledge files. Used in tests only."""
    global _kb_instance
    _kb_instance = None
