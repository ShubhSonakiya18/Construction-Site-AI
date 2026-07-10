"""
verify_sprint6.py — End-to-end manual verification of Sprint 6.

Simulates a complete foreman workflow:
  1. Foreman speaks a voice note (we use a written transcript here)
  2. AI extracts a ConstructionDailyLog from the transcript (Sprint 4 — Groq LLM)
  3. Extracted log is saved to PostgreSQL (Sprint 6 — DailyLogRepository)
  4. AI generates 4 business documents from the log (Sprint 5 — Groq LLM)
  5. Generation outputs are saved to PostgreSQL (Sprint 6 — GenerationRepository)
  6. Everything is queried back from the database and printed

Run:
    python verify_sprint6.py

Requires:
    - DATABASE_URL set in .env (with your PostgreSQL credentials)
    - GROQ_API_KEY set in .env
    - venv active
    - alembic upgrade head already run
    - Seeds already run
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ── Load .env (no python-dotenv needed) ──────────────────────────────────────
def _load_env() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

_load_env()

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"{GREEN}✓ {msg}{RESET}")
def info(msg): print(f"{CYAN}  {msg}{RESET}")
def hdr(msg):  print(f"\n{BOLD}{YELLOW}{'-'*60}{RESET}\n{BOLD}{msg}{RESET}")
def err(msg):  print(f"{RED}✗ {msg}{RESET}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 0 — Check prerequisites
# ─────────────────────────────────────────────────────────────────────────────
hdr("STEP 0 — Checking prerequisites")

if not os.environ.get("DATABASE_URL"):
    err("DATABASE_URL not set. Check your .env file.")
    sys.exit(1)
ok(f"DATABASE_URL = {os.environ['DATABASE_URL'][:50]}...")

if not os.environ.get("GROQ_API_KEY"):
    err("GROQ_API_KEY not set. Check your .env file.")
    sys.exit(1)
ok("GROQ_API_KEY is set")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Connect to PostgreSQL and check tables
# ─────────────────────────────────────────────────────────────────────────────
hdr("STEP 1 — Connecting to PostgreSQL")

from database.session import get_engine, get_session
from database.config import DatabaseConfig
from sqlalchemy import text

config = DatabaseConfig.from_env()
engine = get_engine(config)

with engine.connect() as conn:
    result = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
    ))
    table_count = result.scalar()

ok(f"Connected to PostgreSQL — {table_count} tables found")

with get_session(engine) as session:
    trades_count  = session.execute(text("SELECT COUNT(*) FROM trades")).scalar()
    stages_count  = session.execute(text("SELECT COUNT(*) FROM construction_stages")).scalar()
    company_count = session.execute(text("SELECT COUNT(*) FROM companies")).scalar()

ok(f"Reference data: {trades_count} trades, {stages_count} stages")
ok(f"Demo data: {company_count} company in database")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — AI Extraction (Sprint 4): transcript → ConstructionDailyLog JSON
# ─────────────────────────────────────────────────────────────────────────────
hdr("STEP 2 — AI Extraction (Groq LLM)")

FOREMAN_TRANSCRIPT = """
Good morning, this is David Rivera, foreman for the Johnson Residence project.
Today is July 11th, 2026. We had 8 workers on site today.
Six framing carpenters and two general laborers.

We completed the second floor east and west wall framing — that's about 90 percent done.
We also set the ridge beam for the roof structure.

Materials used: approximately 200 linear feet of 2x6 lumber and 40 sheets of OSB sheathing.
We need more 2x4 studs delivered tomorrow morning — about 150 pieces.

One safety note: a carpenter named Mike slipped on the wet subfloor this morning.
No injury, but we stopped work and put down anti-slip mats.
We held a 10-minute safety meeting about wet surface hazards.

Weather was partly cloudy, 72 degrees. No weather delays.
The electrician subcontractor was delayed by 2 hours — their truck had a flat tire.

Overall the project is about 35 percent complete. Good progress today.
"""

info("Sending transcript to Groq LLM (llama-3.3-70b-versatile)...")
info(f"Transcript length: {len(FOREMAN_TRANSCRIPT.split())} words")

from extraction import ExtractionConfig, ExtractionPipeline

ext_config = ExtractionConfig.from_env()
pipeline = ExtractionPipeline(config=ext_config)
result = pipeline.extract(FOREMAN_TRANSCRIPT)

if not result.success:
    err(f"Extraction failed: {result.error_message}")
    sys.exit(1)

log_dict = result.extracted_log
avg_conf = sum(result.field_confidences.values()) / len(result.field_confidences) if result.field_confidences else 0.0
ok(f"Extraction successful (avg field confidence: {avg_conf:.2f})")
info(f"  log_date:               {log_dict.get('log_date')}")
info(f"  current_stage:          {log_dict.get('current_stage')}")
info(f"  total_workers_present:  {log_dict.get('workforce', {}).get('total_workers_present')}")
info(f"  work_completed items:   {len(log_dict.get('work_completed', []))}")
info(f"  materials_used items:   {len(log_dict.get('materials', {}).get('materials_used', []))}")
info(f"  safety_incidents:       {len(log_dict.get('safety', {}).get('incidents', []))}")
info(f"  delays:                 {len(log_dict.get('delays', []))}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Save to PostgreSQL (Sprint 6): extracted JSON → 12 DB tables
# ─────────────────────────────────────────────────────────────────────────────
hdr("STEP 3 — Saving to PostgreSQL (DailyLogRepository)")

from database.seed.sample_data import PROJECT_ID, SITE_ID, FOREMAN_ID
from database.repositories.daily_log import DailyLogRepository

with get_session(engine) as session:
    repo = DailyLogRepository(session)
    daily_log = repo.create_from_extraction_result(
        extracted_log=log_dict,
        project_id=PROJECT_ID,
        site_id=SITE_ID,
        foreman_id=FOREMAN_ID,
        created_by_id=FOREMAN_ID,
    )
    saved_log_id = daily_log.id
    ok(f"DailyLog saved — ID: {saved_log_id}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Query it back from the database (verify it persisted)
# ─────────────────────────────────────────────────────────────────────────────
hdr("STEP 4 — Reading back from PostgreSQL")

with get_session(engine) as session:
    repo = DailyLogRepository(session)
    loaded = repo.get_with_children(saved_log_id)

    if not loaded:
        err("Could not load the saved log back from the database!")
        sys.exit(1)

ok(f"DailyLog retrieved from DB:")
info(f"  ID:                     {loaded.id}")
info(f"  log_date:               {loaded.log_date}")
info(f"  current_stage:          {loaded.current_stage}")
info(f"  total_workers_present:  {loaded.total_workers_present}")
info(f"  review_status:          {loaded.review_status}")
info(f"  trades_on_site rows:    {len(loaded.trades_on_site)}")
info(f"  work_items rows:        {len(loaded.work_items)}")
info(f"  materials_used rows:    {len(loaded.materials_used)}")
info(f"  safety_incidents rows:  {len(loaded.safety_incidents)}")
info(f"  delays rows:            {len(loaded.delays)}")

if loaded.trades_on_site:
    info("\n  Who was on site:")
    for t in loaded.trades_on_site:
        info(f"    → {t.trade:30s}  {t.workers_count} workers")

if loaded.work_items:
    info("\n  Work completed:")
    for w in loaded.work_items:
        pct = f"{w.task_completion_percent:.0f}%" if w.task_completion_percent else "?"
        info(f"    → [{pct}] {w.task_description}")

if loaded.safety_incidents:
    info("\n  Safety incidents:")
    for s in loaded.safety_incidents:
        info(f"    → {s.incident_type}: {s.description}")

if loaded.delays:
    info("\n  Delays:")
    for d in loaded.delays:
        info(f"    → {d.delay_type}: {d.description} ({d.duration_hours}h)")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — AI Generation (Sprint 5): log → 4 business documents
# ─────────────────────────────────────────────────────────────────────────────
hdr("STEP 5 — AI Generation (4 business documents)")

from generation import AIServiceManager
from generation.config import GenerationConfig

gen_config = GenerationConfig.from_env()
manager = AIServiceManager(config=gen_config)

info("Generating 4 business documents from the extracted log...")
gen_result = manager.generate_all(log_dict)

_service_outputs = [
    ("daily_report",     gen_result.daily_report),
    ("customer_update",  gen_result.customer_update),
    ("safety_talk",      gen_result.safety_talk),
    ("material_reminder",gen_result.material_reminder),
]
ok(f"Generation complete:")
for svc_type, output in _service_outputs:
    word_count = len(output.content.split()) if output and output.content else 0
    status = "✓" if output and output.content else "✗"
    info(f"  {status} {svc_type:25s}  {word_count} words")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — Save generation outputs to PostgreSQL (Sprint 6)
# ─────────────────────────────────────────────────────────────────────────────
hdr("STEP 6 — Saving generation outputs to PostgreSQL")

from database.repositories.generation import GenerationRepository

with get_session(engine) as session:
    gen_repo = GenerationRepository(session)
    saved_count = 0
    for svc_type, output in _service_outputs:
        if output and output.content:
            gen_repo.create_from_service_output(
                daily_log_id=saved_log_id,
                service_output=output,
            )
            saved_count += 1

ok(f"{saved_count} generation outputs saved to generation_outputs table")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 — Query generation outputs back from DB
# ─────────────────────────────────────────────────────────────────────────────
hdr("STEP 7 — Reading generation outputs back from PostgreSQL")

with get_session(engine) as session:
    gen_repo = GenerationRepository(session)
    outputs = gen_repo.list_for_log(saved_log_id)

ok(f"Found {len(outputs)} generation outputs in DB:")
for o in outputs:
    preview = o.content[:80].replace("\n", " ") if o.content else ""
    info(f"  [{o.service_type}]")
    info(f"    Preview: {preview}...")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 8 — Final database count verification
# ─────────────────────────────────────────────────────────────────────────────
hdr("STEP 8 — Final database row counts")

with engine.connect() as conn:
    tables = [
        "daily_logs", "log_trades_on_site", "log_work_items",
        "log_materials_used", "log_materials_required",
        "log_safety_incidents", "log_delays", "generation_outputs",
        "audit_logs",
    ]
    for tbl in tables:
        count = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
        info(f"  {tbl:35s} {count:>4} rows")

# ─────────────────────────────────────────────────────────────────────────────
# DONE
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{BOLD}{GREEN}{'='*60}")
print("  SPRINT 6 VERIFICATION COMPLETE")
print(f"  All systems working end-to-end:")
print(f"  Sprint 4 (Extraction) → Sprint 6 (DB) → Sprint 5 (Generation) → Sprint 6 (DB)")
print(f"{'='*60}{RESET}\n")
print(f"  Daily log ID saved: {saved_log_id}")
print(f"  Query it in pgAdmin:")
print(f"  SELECT * FROM daily_logs WHERE id = '{saved_log_id}';")
print(f"  SELECT trade, workers_count FROM log_trades_on_site WHERE daily_log_id = '{saved_log_id}';")
print(f"  SELECT service_type, LEFT(content, 100) FROM generation_outputs WHERE daily_log_id = '{saved_log_id}';")
