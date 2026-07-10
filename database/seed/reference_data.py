"""
database/seed/reference_data.py — Seed all reference/lookup tables.

These tables are populated once and treated as read-only at runtime.
All values are derived directly from the ConstructionDailyLog v1.0.0 schema
enums and knowledge/construction_ontology.json.

Idempotent: each function checks for existing rows before inserting.
Safe to run multiple times (e.g., after alembic downgrade/upgrade cycles).

Usage:
    from sqlalchemy.orm import Session
    from database.seed.reference_data import seed_all_reference_data

    with get_session() as session:
        seed_all_reference_data(session)
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models.reference import (
    ConstructionStage,
    MaterialCategory,
    PPEType,
    Trade,
)


# ── Trades ────────────────────────────────────────────────────────────────────

_TRADES = [
    {
        "code": "general_labor",
        "display_name": "General Labor",
        "description": "Non-specialized workers who assist all trades with material handling, cleanup, and support tasks.",
        "is_licensed": False,
        "typical_crew_size": 3,
    },
    {
        "code": "concrete",
        "display_name": "Concrete",
        "description": "Specialists in concrete forming, pouring, and finishing. Includes concrete finishers and form carpenters.",
        "is_licensed": False,
        "typical_crew_size": 4,
    },
    {
        "code": "masonry",
        "display_name": "Masonry",
        "description": "Block, brick, and stone masons who build structural and decorative masonry elements.",
        "is_licensed": False,
        "typical_crew_size": 3,
    },
    {
        "code": "framing_carpenter",
        "display_name": "Framing Carpenter",
        "description": "Structural framing specialists who build floor systems, wall assemblies, and roof framing.",
        "is_licensed": False,
        "typical_crew_size": 5,
    },
    {
        "code": "finish_carpenter",
        "display_name": "Finish Carpenter",
        "description": "Specialists in interior trim, doors, millwork, and fine cabinetry installation.",
        "is_licensed": False,
        "typical_crew_size": 2,
    },
    {
        "code": "electrician",
        "display_name": "Electrician",
        "description": "Licensed electrical contractors who install all electrical systems in two phases: rough-in and finish.",
        "is_licensed": True,
        "typical_crew_size": 2,
    },
    {
        "code": "plumber",
        "display_name": "Plumber",
        "description": "Licensed plumbing contractors who install DWV systems and water supply in rough-in and finish phases.",
        "is_licensed": True,
        "typical_crew_size": 2,
    },
    {
        "code": "hvac_technician",
        "display_name": "HVAC Technician",
        "description": "Heating, ventilation, and air conditioning specialists. Install ductwork, equipment, and commission systems.",
        "is_licensed": True,
        "typical_crew_size": 2,
    },
    {
        "code": "roofer",
        "display_name": "Roofer",
        "description": "Roofing specialists who install underlayment, shingles, flashing, and roofing accessories.",
        "is_licensed": False,
        "typical_crew_size": 4,
    },
    {
        "code": "drywall",
        "display_name": "Drywall",
        "description": "Drywall hangers and tapers who install and finish gypsum board systems.",
        "is_licensed": False,
        "typical_crew_size": 3,
    },
    {
        "code": "painter",
        "display_name": "Painter",
        "description": "Interior and exterior painting specialists including prep, prime, and finish coats.",
        "is_licensed": False,
        "typical_crew_size": 3,
    },
    {
        "code": "flooring_installer",
        "display_name": "Flooring Installer",
        "description": "Specialists in hardwood, LVP, carpet, and engineered flooring installation.",
        "is_licensed": False,
        "typical_crew_size": 2,
    },
    {
        "code": "tile_setter",
        "display_name": "Tile Setter",
        "description": "Ceramic, porcelain, and natural stone tile installers for floors, walls, and showers.",
        "is_licensed": False,
        "typical_crew_size": 2,
    },
    {
        "code": "cabinet_installer",
        "display_name": "Cabinet Installer",
        "description": "Kitchen and bathroom cabinet and countertop installation specialists.",
        "is_licensed": False,
        "typical_crew_size": 2,
    },
    {
        "code": "insulation_installer",
        "display_name": "Insulation Installer",
        "description": "Batt, blown, and spray foam insulation installation specialists.",
        "is_licensed": False,
        "typical_crew_size": 2,
    },
    {
        "code": "waterproofing",
        "display_name": "Waterproofing",
        "description": "Foundation and below-grade waterproofing specialists.",
        "is_licensed": False,
        "typical_crew_size": 2,
    },
    {
        "code": "landscaping",
        "display_name": "Landscaping",
        "description": "Grading, topsoil, sod, and landscape planting specialists.",
        "is_licensed": False,
        "typical_crew_size": 3,
    },
    {
        "code": "steel_erector",
        "display_name": "Steel Erector",
        "description": "Structural steel and metal framing specialists.",
        "is_licensed": False,
        "typical_crew_size": 3,
    },
    {
        "code": "welder",
        "display_name": "Welder",
        "description": "Certified welders for structural connections and custom metalwork.",
        "is_licensed": True,
        "typical_crew_size": 1,
    },
    {
        "code": "glazier",
        "display_name": "Glazier",
        "description": "Window, door, and glass installation specialists.",
        "is_licensed": False,
        "typical_crew_size": 2,
    },
    {
        "code": "site_supervisor",
        "display_name": "Site Supervisor",
        "description": "On-site management and coordination for the general contractor.",
        "is_licensed": False,
        "typical_crew_size": 1,
    },
    {
        "code": "safety_officer",
        "display_name": "Safety Officer",
        "description": "Dedicated site safety professional. Conducts toolbox talks and OSHA compliance monitoring.",
        "is_licensed": False,
        "typical_crew_size": 1,
    },
    {
        "code": "project_manager",
        "display_name": "Project Manager",
        "description": "Off-site or visiting project management staff.",
        "is_licensed": False,
        "typical_crew_size": 1,
    },
    {
        "code": "surveyor",
        "display_name": "Surveyor",
        "description": "Licensed land surveyors for lot lines, setbacks, and grade stakes.",
        "is_licensed": True,
        "typical_crew_size": 2,
    },
    {
        "code": "other",
        "display_name": "Other",
        "description": "Any trade not covered by the above categories.",
        "is_licensed": False,
        "typical_crew_size": 1,
    },
]


# ── Construction Stages ───────────────────────────────────────────────────────

_STAGES = [
    {"code": "site_preparation",        "display_name": "Site Preparation",          "description": "Clearing, grading, excavation, and utility marking.", "sequence_order": 1,  "typical_duration_days": 5},
    {"code": "foundation",              "display_name": "Foundation",                 "description": "Footing excavation, forming, concrete pour, and cure.", "sequence_order": 2,  "typical_duration_days": 10},
    {"code": "concrete_flatwork",       "display_name": "Concrete Flatwork",          "description": "Garage slab, driveway, sidewalks, and patio pours.", "sequence_order": 3,  "typical_duration_days": 5},
    {"code": "framing",                 "display_name": "Framing",                   "description": "Floor, wall, and roof framing including sheathing and windows.", "sequence_order": 4,  "typical_duration_days": 15},
    {"code": "roofing",                 "display_name": "Roofing",                   "description": "Roof decking, underlayment, shingles, and flashing.", "sequence_order": 5,  "typical_duration_days": 5},
    {"code": "electrical_rough_in",     "display_name": "Electrical Rough-In",        "description": "Panel installation, conduit, wiring, and box setting.", "sequence_order": 6,  "typical_duration_days": 7},
    {"code": "hvac_rough_in",           "display_name": "HVAC Rough-In",              "description": "Ductwork, air handler, and equipment rough installation.", "sequence_order": 7,  "typical_duration_days": 7},
    {"code": "plumbing_rough_in",       "display_name": "Plumbing Rough-In",          "description": "DWV stack, water supply, and tub/shower installation.", "sequence_order": 8,  "typical_duration_days": 7},
    {"code": "insulation",              "display_name": "Insulation",                 "description": "Batt, blown, and spray foam insulation installation.", "sequence_order": 9,  "typical_duration_days": 3},
    {"code": "drywall",                 "display_name": "Drywall",                   "description": "Drywall hanging, taping, mudding, and sanding.", "sequence_order": 10, "typical_duration_days": 10},
    {"code": "painting",                "display_name": "Painting",                  "description": "Prime and finish coats, interior and exterior.", "sequence_order": 11, "typical_duration_days": 7},
    {"code": "electrical_finish",       "display_name": "Electrical Finish",          "description": "Device installation, trim, panel terminations, and trim-out.", "sequence_order": 12, "typical_duration_days": 3},
    {"code": "hvac_finish",             "display_name": "HVAC Finish",               "description": "Register installation, equipment commissioning, and testing.", "sequence_order": 13, "typical_duration_days": 3},
    {"code": "plumbing_finish",         "display_name": "Plumbing Finish",            "description": "Fixture installation, trim-out, and pressure testing.", "sequence_order": 14, "typical_duration_days": 3},
    {"code": "flooring",                "display_name": "Flooring",                  "description": "Hardwood, LVP, tile, and carpet installation.", "sequence_order": 15, "typical_duration_days": 7},
    {"code": "trim_and_millwork",       "display_name": "Trim and Millwork",          "description": "Baseboard, casing, crown molding, and interior doors.", "sequence_order": 16, "typical_duration_days": 5},
    {"code": "cabinets_and_countertops","display_name": "Cabinets and Countertops",   "description": "Kitchen and bathroom cabinet, countertop, and hardware installation.", "sequence_order": 17, "typical_duration_days": 5},
    {"code": "tile_work",               "display_name": "Tile Work",                 "description": "Floor, wall, and shower tile installation and grouting.", "sequence_order": 18, "typical_duration_days": 7},
    {"code": "final_cleanup",           "display_name": "Final Cleanup",              "description": "Construction debris removal, punch list cleaning.", "sequence_order": 19, "typical_duration_days": 2},
    {"code": "inspection",              "display_name": "Inspection",                "description": "AHJ inspections including final and certificate of occupancy.", "sequence_order": 20, "typical_duration_days": 1},
    {"code": "punch_list",              "display_name": "Punch List",                "description": "Correction of deficiency items identified at walkthrough.", "sequence_order": 21, "typical_duration_days": 5},
    {"code": "project_closeout",        "display_name": "Project Closeout",           "description": "Final walkthroughs, documentation delivery, and owner handover.", "sequence_order": 22, "typical_duration_days": 2},
]


# ── Material Categories ───────────────────────────────────────────────────────

_MATERIAL_CATEGORIES = [
    {"code": "concrete",        "display_name": "Concrete",            "description": "Ready-mix concrete, concrete block, and masonry units."},
    {"code": "masonry",         "display_name": "Masonry",             "description": "Brick, block, mortar, and masonry accessories."},
    {"code": "lumber",          "display_name": "Lumber",              "description": "Dimensional lumber, engineered lumber, OSB, and plywood."},
    {"code": "steel_metal",     "display_name": "Steel / Metal",       "description": "Structural steel, metal framing, fasteners, and hardware."},
    {"code": "roofing",         "display_name": "Roofing",             "description": "Shingles, underlayment, flashing, and roofing accessories."},
    {"code": "electrical",      "display_name": "Electrical",          "description": "Wire, conduit, panels, devices, and electrical fixtures."},
    {"code": "plumbing",        "display_name": "Plumbing",            "description": "Pipe, fittings, fixtures, and plumbing accessories."},
    {"code": "hvac",            "display_name": "HVAC",                "description": "Ductwork, equipment, registers, and HVAC accessories."},
    {"code": "insulation",      "display_name": "Insulation",          "description": "Batt, blown, rigid foam, and spray foam insulation."},
    {"code": "drywall",         "display_name": "Drywall",             "description": "Gypsum board, corner bead, joint compound, and tape."},
    {"code": "flooring",        "display_name": "Flooring",            "description": "Hardwood, LVP, tile, carpet, and underlayment."},
    {"code": "paint_coatings",  "display_name": "Paint / Coatings",    "description": "Interior and exterior paints, primers, and specialty coatings."},
    {"code": "hardware",        "display_name": "Hardware",            "description": "Door hardware, fasteners, anchors, and general construction hardware."},
    {"code": "finishes",        "display_name": "Finishes",            "description": "Trim, millwork, cabinets, countertops, and interior finish materials."},
    {"code": "safety_equipment","display_name": "Safety Equipment",    "description": "PPE, temporary barriers, fall protection, and safety supplies."},
    {"code": "other",           "display_name": "Other",               "description": "Materials not covered by other categories."},
]


# ── PPE Types ─────────────────────────────────────────────────────────────────

_PPE_TYPES = [
    {"code": "hard_hat",                "display_name": "Hard Hat",                 "osha_reference": "29 CFR 1926.100"},
    {"code": "high_vis_vest",           "display_name": "High-Visibility Vest",      "osha_reference": "29 CFR 1926.201"},
    {"code": "safety_glasses",          "display_name": "Safety Glasses",            "osha_reference": "29 CFR 1926.102"},
    {"code": "face_shield",             "display_name": "Face Shield",               "osha_reference": "29 CFR 1926.102"},
    {"code": "leather_gloves",          "display_name": "Leather Gloves",            "osha_reference": "29 CFR 1926.28"},
    {"code": "rubber_gloves",           "display_name": "Rubber Gloves",             "osha_reference": "29 CFR 1926.137"},
    {"code": "cut_resistant_gloves",    "display_name": "Cut-Resistant Gloves",      "osha_reference": "29 CFR 1926.28"},
    {"code": "steel_toe_boots",         "display_name": "Steel-Toe Boots",           "osha_reference": "29 CFR 1926.96"},
    {"code": "rubber_boots",            "display_name": "Rubber Boots",              "osha_reference": "29 CFR 1926.96"},
    {"code": "hearing_protection",      "display_name": "Hearing Protection",        "osha_reference": "29 CFR 1926.52"},
    {"code": "n95_respirator",          "display_name": "N95 Respirator",            "osha_reference": "29 CFR 1926.103"},
    {"code": "half_face_respirator",    "display_name": "Half-Face Respirator",      "osha_reference": "29 CFR 1926.103"},
    {"code": "full_face_respirator",    "display_name": "Full-Face Respirator",      "osha_reference": "29 CFR 1926.103"},
    {"code": "fall_protection_harness", "display_name": "Fall Protection Harness",   "osha_reference": "29 CFR 1926.502"},
    {"code": "knee_pads",               "display_name": "Knee Pads",                 "osha_reference": "29 CFR 1926.28"},
    {"code": "arc_flash_ppe",           "display_name": "Arc Flash PPE",             "osha_reference": "29 CFR 1910.269"},
]


# ── Seed Functions ────────────────────────────────────────────────────────────

# Public aliases so tests and CLI scripts can introspect counts without importing private names
TRADES = _TRADES
CONSTRUCTION_STAGES = _STAGES
MATERIAL_CATEGORIES = _MATERIAL_CATEGORIES
PPE_TYPES = _PPE_TYPES


def seed_trades(session: Session) -> int:
    """Insert all trade records. Returns number of records inserted."""
    inserted = 0
    for data in _TRADES:
        exists = session.execute(
            select(Trade).where(Trade.code == data["code"])
        ).scalar_one_or_none()
        if exists is None:
            session.add(Trade(**data))
            inserted += 1
    session.flush()
    return inserted


def seed_construction_stages(session: Session) -> int:
    """Insert all construction stage records. Returns number inserted."""
    inserted = 0
    for data in _STAGES:
        exists = session.execute(
            select(ConstructionStage).where(ConstructionStage.code == data["code"])
        ).scalar_one_or_none()
        if exists is None:
            session.add(ConstructionStage(**data))
            inserted += 1
    session.flush()
    return inserted


def seed_material_categories(session: Session) -> int:
    """Insert all material category records. Returns number inserted."""
    inserted = 0
    for data in _MATERIAL_CATEGORIES:
        exists = session.execute(
            select(MaterialCategory).where(MaterialCategory.code == data["code"])
        ).scalar_one_or_none()
        if exists is None:
            session.add(MaterialCategory(**data))
            inserted += 1
    session.flush()
    return inserted


def seed_ppe_types(session: Session) -> int:
    """Insert all PPE type records. Returns number inserted."""
    inserted = 0
    for data in _PPE_TYPES:
        exists = session.execute(
            select(PPEType).where(PPEType.code == data["code"])
        ).scalar_one_or_none()
        if exists is None:
            session.add(PPEType(**data))
            inserted += 1
    session.flush()
    return inserted


def seed_all_reference_data(session: Session) -> dict[str, int]:
    """Seed all reference tables. Returns counts of inserted records per table.

    Idempotent: existing records are skipped, never duplicated.

    Usage:
        with get_session() as session:
            counts = seed_all_reference_data(session)
        print(counts)
        # {'trades': 25, 'construction_stages': 22, 'material_categories': 16, 'ppe_types': 16}
    """
    return {
        "trades": seed_trades(session),
        "construction_stages": seed_construction_stages(session),
        "material_categories": seed_material_categories(session),
        "ppe_types": seed_ppe_types(session),
    }
