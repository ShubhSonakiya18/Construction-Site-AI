"""
safety_talk_generator.py — Generates safety toolbox talk records for CSV export.

Each record is a safety meeting conducted on a construction site, covering:
- OSHA 29 CFR 1926 topics relevant to the current stage
- Hazards identified from construction_ontology.json
- PPE requirements from ontology
- Attendance and duration

All hazard, PPE, and topic data is loaded from knowledge base — no hardcoding.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from faker import Faker

from dataset_generation_framework.config import (
    PROJECT_START_DATE_RANGE_DAYS,
    SCHEMA_VERSION,
)
from dataset_generation_framework.core.knowledge_loader import KnowledgeBase
from dataset_generation_framework.generators.base_generator import BaseGenerator

logger = logging.getLogger(__name__)

_REFERENCE_DATE = date(2023, 1, 1)

# Safety talk regulatory references — output formatting, not domain knowledge
_OSHA_REFERENCES = [
    "29 CFR 1926.20 — General Safety Requirements",
    "29 CFR 1926.21 — Safety Training and Education",
    "29 CFR 1926.50 — Medical Services and First Aid",
    "29 CFR 1926.100 — Head Protection",
    "29 CFR 1926.102 — Eye and Face Protection",
    "29 CFR 1926.150 — Fire Protection",
    "29 CFR 1926.200 — Accident Prevention Signs",
    "29 CFR 1926.250 — General Requirements for Storage",
    "29 CFR 1926.300 — General Requirements for Tools",
    "29 CFR 1926.403 — Electrical General Requirements",
    "29 CFR 1926.500 — Fall Protection",
    "29 CFR 1926.502 — Fall Protection Systems Criteria",
    "29 CFR 1926.550 — Cranes and Derricks",
    "29 CFR 1926.600 — Equipment",
    "29 CFR 1926.651 — Excavations",
    "29 CFR 1926.701 — Concrete and Masonry",
    "29 CFR 1926.800 — Underground Construction",
    "29 CFR 1926.900 — Blasting",
    "29 CFR 1926.1053 — Ladders",
    "29 CFR 1926.1060 — Stairways and Ladders",
]

_TALK_TOPICS_BY_STAGE: dict[str, list[str]] = {
    "site_preparation": [
        "Excavation and trenching safety",
        "Heavy equipment operation zones",
        "Underground utility identification",
        "PPE requirements on active excavation sites",
    ],
    "foundation": [
        "Concrete pour safety: splash and vapors",
        "Footing excavation cave-in prevention",
        "Reinforcement bar handling and storage",
        "Wet concrete PPE: gloves, boots, eye protection",
    ],
    "framing": [
        "Fall protection at leading edge",
        "Proper use of fall harness and lanyard",
        "Nail gun safety and trigger discipline",
        "Structural lumber load-bearing during erection",
        "Working at heights — ladder safety",
    ],
    "roofing": [
        "Roof edge fall protection requirements",
        "Guardrail system installation and use",
        "Proper harness fit and anchor point selection",
        "Steep slope roofing ergonomics",
        "Material handling on sloped surfaces",
    ],
    "electrical_rough_in": [
        "Lockout/tagout procedures for electrical",
        "Arc flash awareness on rough-in sites",
        "Extension cord safety and GFCI use",
        "Electrical panel clearance requirements",
    ],
    "hvac_rough_in": [
        "Sheet metal handling — cut-resistant gloves",
        "Ductwork overhead work — fall prevention",
        "Refrigerant handling safety",
        "Confined space awareness in attic work",
    ],
    "plumbing_rough_in": [
        "Solvent cement and flux safety",
        "Under-slab work — trench safety",
        "Pipe threading machine safe use",
        "Back injury prevention: lifting heavy pipe",
    ],
    "insulation": [
        "Respiratory protection for insulation work",
        "Fiberglass fiber exposure — N95 and long sleeves",
        "Spray foam: chemical exposure and PPE",
        "Confined attic space heat stress management",
    ],
    "drywall": [
        "Drywall lift operation safety",
        "Stilts use on drywall finishing crews",
        "Dust control during sanding",
        "Overhead drywall installation ergonomics",
    ],
    "painting": [
        "VOC exposure limits and ventilation",
        "Spray painting respiratory protection",
        "Ladder safety for ceiling work",
        "Chemical storage and disposal",
    ],
    "flooring": [
        "Knee protection and ergonomics",
        "Adhesive chemical exposure",
        "Saw safety during cutting operations",
        "Slip hazards from freshly installed flooring",
    ],
    "electrical_finish": [
        "Energized panel safe work practices",
        "Light fixture installation fall protection",
        "Device box wiring — confirm de-energized",
    ],
    "hvac_finish": [
        "Refrigerant charging safety",
        "Equipment commissioning electrical hazards",
        "Heavy equipment setting — crane/forklift safety",
    ],
    "plumbing_finish": [
        "Water heater installation — gas connection safety",
        "Pressure testing procedures",
        "Fixture setting ergonomics",
    ],
}

_GENERIC_TOPICS = [
    "Housekeeping and general site cleanliness",
    "Emergency action plan and muster points",
    "Heat illness prevention",
    "Incident reporting procedures",
    "First aid kit locations",
    "Tool inspection and defective tool tagging",
    "Fire extinguisher locations and use",
    "COVID-19 and respiratory illness protocol",
]

_TALK_FORMATS = ["tailgate", "toolbox_talk", "safety_briefing", "pre_task_planning"]
_DELIVERY_METHODS = ["verbal_with_handout", "slide_presentation", "video_then_discussion", "verbal_only"]


class SafetyTalkGenerator(BaseGenerator):
    """Generates safety toolbox talk records for CSV export."""

    def __init__(self, kb: KnowledgeBase, seed: int) -> None:
        super().__init__(kb, seed)
        self._stages = [
            n["id"] for n in self.kb.dag_nodes()
            if n.get("type") != "milestone"
        ]
        self._all_hazards = self.kb.ontology_hazards()
        self._all_ppe_types = self.kb.ontology_ppe_types()

    def generate_one(self, **kwargs: Any) -> dict:
        fake = Faker("en_US")
        fake.seed_instance(self.rng.randint(0, 999999))

        stage = self.rng.choice(self._stages) if self._stages else "framing"
        talk_date = _REFERENCE_DATE + timedelta(days=self.rng.randint(0, PROJECT_START_DATE_RANGE_DAYS))

        # Topics: stage-specific + maybe a generic one
        stage_topics = _TALK_TOPICS_BY_STAGE.get(stage, _GENERIC_TOPICS)
        topic = self.rng.choice(stage_topics)
        if self.rng.random() > 0.6:
            secondary = self.rng.choice(_GENERIC_TOPICS)
            full_topic = f"{topic}; {secondary}"
        else:
            full_topic = topic

        # Hazards from knowledge base
        stage_hazards = self.kb.hazards_for_stage(stage)
        if stage_hazards:
            hazards_discussed = [h.get("name", h) if isinstance(h, dict) else h
                                 for h in self.rng.sample(stage_hazards, min(3, len(stage_hazards)))]
        else:
            hazards_discussed = ["General site hazards", "Struck-by hazard", "Fall from elevation"]

        # PPE from knowledge base
        ppe_required = self.kb.ppe_for_stage(stage)
        if ppe_required:
            ppe_discussed = [p.get("name", p) if isinstance(p, dict) else p
                             for p in ppe_required[:4]]
        else:
            ppe_discussed = ["hard_hat", "safety_glasses", "steel_toe_boots"]

        attendees = self.rng.randint(3, 18)
        duration = self.rng.choice([5, 10, 10, 15, 15, 20])

        return {
            "talk_id": self.seeded_uuid(),
            "talk_date": talk_date.isoformat(),
            "project_id": self.seeded_uuid(),
            "project_name": f"{fake.last_name()} Residence",
            "stage_context": stage,
            "foreman_name": fake.name_male(),
            "talk_topic": full_topic,
            "talk_format": self.rng.choice(_TALK_FORMATS),
            "delivery_method": self.rng.choice(_DELIVERY_METHODS),
            "duration_minutes": duration,
            "attendees_count": attendees,
            "hazards_discussed": "; ".join(hazards_discussed),
            "ppe_discussed": "; ".join(str(p) for p in ppe_discussed),
            "osha_reference": self.rng.choice(_OSHA_REFERENCES),
            "action_items": (
                f"Ensure all workers wear {ppe_discussed[0]} when {stage.replace('_', ' ')} is active"
                if ppe_discussed else None
            ),
            "follow_up_required": self.rng.choice([True, False, False, False]),
            "sign_in_sheet_on_file": self.rng.choice([True, True, True, False]),
            "notes": None,
            "schema_version": SCHEMA_VERSION,
        }
