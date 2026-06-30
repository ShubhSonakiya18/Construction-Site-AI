"""
config.py — Single source of truth for all generation parameters.

To scale from 5,000 to 500,000+ records, change ONLY the size constants below.
Zero business logic lives here. Zero construction knowledge lives here.
Business logic lives in generators. Construction knowledge lives in knowledge/.

Architecture rule: If a value could ever need to change for a new run or a
different scale, it lives here — not buried in a generator function.
"""
from pathlib import Path

# ── Project Root ───────────────────────────────────────────────────────────────
# Resolved at import time so all modules agree on the root regardless of CWD.
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# ── Knowledge Base Paths ───────────────────────────────────────────────────────
# Never import knowledge content directly. Always use KnowledgeBase singleton.
KNOWLEDGE_BASE_DIR = PROJECT_ROOT / "knowledge"

KNOWLEDGE_FILES = {
    "schema":             KNOWLEDGE_BASE_DIR / "construction_daily_log_schema.json",
    "stages":             KNOWLEDGE_BASE_DIR / "construction_stages.json",
    "dependency_graph":   KNOWLEDGE_BASE_DIR / "dependency_graph.json",
    "construction_rules": KNOWLEDGE_BASE_DIR / "construction_rules.json",
    "validation_rules":   KNOWLEDGE_BASE_DIR / "validation_rules.json",
    "ontology":           KNOWLEDGE_BASE_DIR / "construction_ontology.json",
}

# ── Dataset Output Directories ─────────────────────────────────────────────────
# raw/       → intermediate records before validation (written by generators)
# generated/ → all generated records regardless of validation status
# validated/ → only records that passed all validation phases
# exports/   → final consumer-ready files (JSONL, CSV) in their final schema
DATASETS_DIR  = PROJECT_ROOT / "datasets"
RAW_DIR       = DATASETS_DIR / "raw"
GENERATED_DIR = DATASETS_DIR / "generated"
VALIDATED_DIR = DATASETS_DIR / "validated"
EXPORTS_DIR   = DATASETS_DIR / "exports"

# ── Dataset Sizes ──────────────────────────────────────────────────────────────
# THE ONLY VALUES YOU CHANGE TO SCALE OUTPUT.
# All generator loops, project counts, and batch sizes derive from these.
DAILY_LOG_COUNT       = 5_000   # → datasets/exports/daily_logs_v1.jsonl
SCHEDULE_COUNT        = 1_000   # → datasets/exports/project_schedules_v1.jsonl
CUSTOMER_UPDATE_COUNT = 1_000   # → datasets/exports/customer_updates_v1.jsonl
SAFETY_TALK_COUNT     = 200     # → datasets/exports/safety_talks_v1.csv
MATERIAL_COUNT        = 500     # → datasets/exports/materials_v1.csv

# ── Project Simulation Parameters ─────────────────────────────────────────────
# LOGS_PER_PROJECT controls how many working days each simulated project spans.
# Projects count is derived: ceil(DAILY_LOG_COUNT / LOGS_PER_PROJECT)
# Changing DAILY_LOG_COUNT automatically adjusts number of projects.
LOGS_PER_PROJECT      = 100     # working days per project (realistic: 97 critical path days)
MAX_LOGS_PER_PROJECT  = 150     # safety cap — prevents infinite loops on slow projects

# ── Reproducibility ────────────────────────────────────────────────────────────
DEFAULT_SEED = 42               # --seed CLI flag overrides this

# ── Performance ────────────────────────────────────────────────────────────────
# BATCH_SIZE: records accumulated in memory before flushing to disk.
# Safe for 500k+ runs. Never loads all records into memory simultaneously.
BATCH_SIZE = 1_000

# VALIDATE_EVERY_N: validate every Nth record.
# 1 = validate all (default, use for small runs).
# 10 = validate 10% (use for 100k+ runs where speed matters).
VALIDATE_EVERY_N = 1

# ── Schema Constants ───────────────────────────────────────────────────────────
SCHEMA_VERSION = "1.0.0"
LOG_SOURCE_SYNTHETIC = "voice_recording"   # generated logs simulate voice notes
REVIEW_STATUS_DEFAULT = "approved"         # synthetic data is pre-approved

# ── Project Generation Ranges ──────────────────────────────────────────────────
PROJECT_START_DATE_RANGE_DAYS = 730        # projects start within a 2-year window
PROJECT_SIZE_SQFT_MIN = 1_200
PROJECT_SIZE_SQFT_MAX = 5_000
CONTRACT_VALUE_MIN_USD = 150_000
CONTRACT_VALUE_MAX_USD = 800_000
DAILY_LABOR_COST_PER_WORKER = 350         # USD/day/worker (rough average)
DAILY_MATERIAL_COST_BASE = 800            # USD/day base during active stages

# ── Weather Probabilities (independent per day, per project) ───────────────────
# Tuned so rain stays under VAL-WTH-004 limit of 30% per project.
# These are sampled with rng.choices() in weather generation.
WEATHER_CONDITIONS = [
    "sunny", "partly_cloudy", "overcast", "foggy",
    "drizzle", "rainy", "heavy_rain", "windy",
]
WEATHER_WEIGHTS = [
    0.40,   # sunny
    0.25,   # partly_cloudy
    0.15,   # overcast
    0.05,   # foggy
    0.05,   # drizzle
    0.05,   # rainy         ← kept low to respect VAL-WTH-004
    0.02,   # heavy_rain
    0.03,   # windy
]
# Must sum to 1.0. Validated at import time below.
assert abs(sum(WEATHER_WEIGHTS) - 1.0) < 1e-9, "WEATHER_WEIGHTS must sum to 1.0"

# Weather conditions that completely stop outdoor work (foundation/roofing)
WORK_STOPPING_CONDITIONS = {"rainy", "heavy_rain", "thunderstorm", "snowy", "icy", "hail"}

# Productivity modifier per weather condition (1.0 = full, 0.0 = no work)
WEATHER_PRODUCTIVITY = {
    "sunny": 1.0,
    "partly_cloudy": 1.0,
    "overcast": 0.95,
    "foggy": 0.85,
    "drizzle": 0.80,
    "rainy": 0.30,        # indoor work may continue; outdoor stops
    "heavy_rain": 0.10,   # near-zero productivity
    "thunderstorm": 0.0,
    "snowy": 0.20,
    "icy": 0.0,
    "windy": 0.75,
    "hail": 0.0,
}

# ── Event Probabilities (per log) ─────────────────────────────────────────────
DELAY_PROBABILITY         = 0.10   # 10% of logs have at least one delay
INSPECTION_PROBABILITY    = 0.05   # 5% of logs include an inspection
SAFETY_INCIDENT_PROB      = 0.02   # 2% of logs have safety incidents
SAFETY_MEETING_PROB       = 0.40   # 40% of logs include a safety meeting
CLIENT_CONTACT_PROB       = 0.15   # 15% mention client contact today
LATE_ARRIVAL_PROB         = 0.12   # 12% have at least one late arrival
EQUIPMENT_USED_PROB       = 0.35   # 35% of logs have equipment entries

# ── Stage Duration Variance ────────────────────────────────────────────────────
# Multiply typical_duration_days by a factor in [min, max] to simulate variability.
STAGE_DURATION_VARIANCE = (0.85, 1.30)

# Outdoor stages where rain stops all productive work (maps to productivity=0)
WEATHER_SENSITIVE_OUTDOOR_STAGES = {
    "site_preparation", "foundation", "concrete_flatwork", "framing", "roofing"
}

# ── USA States for Site Addresses ──────────────────────────────────────────────
# Weighted toward high-construction-volume states
USA_STATES = [
    "TX", "FL", "CA", "AZ", "GA", "NC", "CO", "TN",
    "SC", "NV", "WA", "OR", "UT", "ID", "MT",
]

# ── Customer Update Templates ─────────────────────────────────────────────────
# Number of template variations per stage to avoid repetitive AI training data
CUSTOMER_UPDATE_TEMPLATE_VARIATIONS = 5
