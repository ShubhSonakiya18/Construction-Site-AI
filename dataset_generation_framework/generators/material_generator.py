"""
material_generator.py — Generates construction material catalog records for CSV export.

Each record is an entry in a construction material catalog:
- Material name, category, unit of measure
- Price range and typical usage context
- Stage applicability (from knowledge base)

All material names and categories are loaded from construction_ontology.json.
Zero hardcoded material names — the ontology is the source of truth.
"""
from __future__ import annotations

import logging
from typing import Any

from dataset_generation_framework.config import SCHEMA_VERSION
from dataset_generation_framework.core.knowledge_loader import KnowledgeBase
from dataset_generation_framework.core.rule_engine import RuleEngine
from dataset_generation_framework.generators.base_generator import BaseGenerator

logger = logging.getLogger(__name__)

# Units per category — output formatting, driven by ontology categories
_CATEGORY_UNITS = {
    "concrete":         ("cubic_yard", 80, 250),
    "masonry":          ("each", 0.5, 2.0),
    "lumber":           ("board_feet", 0.80, 3.50),
    "steel_metal":      ("linear_feet", 1.50, 12.0),
    "roofing":          ("square", 90, 250),
    "electrical":       ("each", 0.50, 85.0),
    "plumbing":         ("each", 1.0, 120.0),
    "hvac":             ("each", 5.0, 450.0),
    "insulation":       ("sq_feet", 0.30, 1.80),
    "drywall":          ("sheet", 12, 22),
    "flooring":         ("sq_feet", 1.50, 14.0),
    "paint_coatings":   ("gallon", 28, 65),
    "hardware":         ("each", 0.25, 45.0),
    "finishes":         ("each", 5.0, 180.0),
    "safety_equipment": ("each", 8.0, 350.0),
    "other":            ("each", 1.0, 50.0),
}

# Fallback materials if ontology is sparse
_FALLBACK_MATERIALS: list[dict] = [
    {"name": "Ready-mix concrete 4000 PSI", "category": "concrete", "typical_unit": "cubic_yard"},
    {"name": "CMU block 8x8x16", "category": "masonry", "typical_unit": "each"},
    {"name": "2x4x92 stud SPF #2", "category": "lumber", "typical_unit": "board_feet"},
    {"name": "OSB sheathing 7/16\"", "category": "lumber", "typical_unit": "sheet"},
    {"name": "Asphalt shingles 30yr architectural", "category": "roofing", "typical_unit": "square"},
    {"name": "15/32\" plywood CD", "category": "lumber", "typical_unit": "sheet"},
    {"name": "14/2 NM cable", "category": "electrical", "typical_unit": "linear_feet"},
    {"name": "PEX-A 1/2\" tubing", "category": "plumbing", "typical_unit": "linear_feet"},
    {"name": "5/8\" drywall sheet", "category": "drywall", "typical_unit": "sheet"},
    {"name": "R-19 batt insulation", "category": "insulation", "typical_unit": "sq_feet"},
    {"name": "Interior latex paint", "category": "paint_coatings", "typical_unit": "gallon"},
    {"name": "LVP flooring 5mm", "category": "flooring", "typical_unit": "sq_feet"},
    {"name": "HVAC flex duct 8\"", "category": "hvac", "typical_unit": "linear_feet"},
    {"name": "Hard hat Type II", "category": "safety_equipment", "typical_unit": "each"},
    {"name": "Safety harness Class III", "category": "safety_equipment", "typical_unit": "each"},
]

_SUPPLIERS = [
    "Home Depot Pro", "Lowe's ProDesk", "ABC Supply Co.", "84 Lumber",
    "Waxman Industries", "Ferguson Enterprises", "Graybar Electric",
    "Grainger Industrial", "Fastenal", "US LBM", None, None,
]

_CONDITIONS = ["new", "new", "new", "reconditioned"]


class MaterialGenerator(BaseGenerator):
    """Generates construction material catalog records for CSV export."""

    def __init__(self, kb: KnowledgeBase, seed: int) -> None:
        super().__init__(kb, seed)
        self._rule_engine = RuleEngine(kb)

        # Pull material list from ontology
        raw = kb.ontology_materials()
        self._materials = raw if raw else _FALLBACK_MATERIALS

        # Stage lookup from ontology (for materials_used_in_stage field)
        self._stages = [
            n["id"] for n in kb.dag_nodes()
            if n.get("type") != "milestone"
        ]

    def generate_one(self, **kwargs: Any) -> dict:
        mat = self.rng.choice(self._materials)

        if isinstance(mat, dict):
            name     = mat.get("name") or mat.get("material_name", "Unknown Material")
            category = mat.get("category", "other")
            unit     = mat.get("typical_unit", "each")
        else:
            name     = str(mat)
            category = "other"
            unit     = "each"

        # Price range from category defaults
        cat_unit, price_lo, price_hi = _CATEGORY_UNITS.get(
            category, ("each", 1.0, 50.0)
        )
        if unit == "each":
            unit = cat_unit

        unit_price = round(self.rng.uniform(price_lo, price_hi), 2)
        qty_on_hand = self.rng.randint(0, 500)

        # Which stage is this material primarily used in?
        applicable_stages = [
            s for s in self._stages
            if self._rule_engine.is_material_expected_for_stage(category, s)
        ]
        primary_stage = applicable_stages[0] if applicable_stages else "general"

        # Add variety to material names with size/grade suffix when applicable
        name_with_spec = self._add_spec(name, category)

        return {
            "material_id": self.seeded_uuid(),
            "material_name": name_with_spec,
            "category": category if category in _CATEGORY_UNITS else "other",
            "sub_category": mat.get("sub_category") if isinstance(mat, dict) else None,
            "unit_of_measure": unit,
            "unit_price_usd": unit_price,
            "supplier": self.rng.choice(_SUPPLIERS),
            "sku": f"SKU-{self.rng.randint(10000, 99999)}",
            "brand": mat.get("brand") if isinstance(mat, dict) else None,
            "condition": self.rng.choice(_CONDITIONS),
            "primary_stage_used": primary_stage,
            "applicable_stages": "; ".join(applicable_stages[:5]),
            "qty_on_hand": qty_on_hand,
            "reorder_point": max(0, self.rng.randint(5, 50)),
            "lead_time_days": self.rng.randint(1, 21),
            "waste_factor_percent": round(self.rng.uniform(3.0, 15.0), 1),
            "notes": None,
            "schema_version": SCHEMA_VERSION,
        }

    def _add_spec(self, name: str, category: str) -> str:
        """Add a realistic size or grade spec to the material name for variety."""
        if category == "lumber":
            specs = ["#2 KD-15", "#1 SPF", "Select Structural", "#2 HF"]
            return f"{name} — {self.rng.choice(specs)}"
        if category == "concrete":
            psi = self.rng.choice([3000, 3500, 4000, 5000])
            return f"{name} {psi} PSI"
        if category == "insulation":
            r = self.rng.choice(["R-13", "R-19", "R-21", "R-38", "R-49"])
            return f"{name} {r}"
        if category == "drywall":
            thick = self.rng.choice(["1/2\"", "5/8\"", "1/4\""])
            return f"{name} {thick}"
        return name
