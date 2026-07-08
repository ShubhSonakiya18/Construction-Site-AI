# Next Sprint: Sprint 6 — Database Design

**Status:** AWAITING SPRINT 5 APPROVAL — Do not begin until Sprint 5 is approved.
**Prerequisites:** Sprint 5 APPROVED and FROZEN
**Supersedes:** Sprint 5 spec (now complete — see `generation/` package and `docs/AI_SERVICES.md`)

---

## Context: Why Sprint 6

Sprint 5 produces 4 AI-generated text outputs from a `ConstructionDailyLog`.
Sprint 6 designs the PostgreSQL schema and ORM models so those outputs —
plus the structured log itself — can be persisted and queried.

```
[Sprint 3 — DONE: speech/ → SpeechProcessingResult]
    ↓
[Sprint 4 — DONE: extraction/ → ExtractionResult (ConstructionDailyLog)]
    ↓
[Sprint 5 — DONE: generation/ → GenerationResult (4 AI outputs)]
    ↓
[Sprint 6: Database — PostgreSQL schema + SQLAlchemy ORM + Alembic migrations]
    ↓
[Sprint 7: FastAPI backend + Celery async processing]
```

---

## Sprint 6 Objectives

### 1. PostgreSQL Schema Design
- Tables mirroring the 12 sections of `ConstructionDailyLog` v1.0.0
- AI generation outputs stored in a `generation_outputs` table (linked to `daily_logs`)
- UUID v4 primary keys throughout (consistent with the JSON schema)
- Proper foreign keys, indexes, and constraints

### 2. SQLAlchemy ORM Models
- Declarative Base + typed models for all tables
- Relationship definitions (`relationship()`, `ForeignKey`)
- `to_dict()` / `from_dict()` methods for each model
- No circular imports

### 3. Alembic Migrations
- Initial migration: create all tables
- Migration scripts auto-generated from ORM models
- Reversible (upgrade + downgrade)
- Seed script: insert 5 sample `ConstructionDailyLog` records

### 4. ER Diagram
- Entity-Relationship diagram for all tables
- Documented in `docs/DATABASE.md`

### 5. Integration with Sprints 4 + 5
- `ExtractionResult.extracted_log` → save to `daily_logs` table
- `GenerationResult` → save to `generation_outputs` table
- `SpeechProcessingResult` metadata → save to `audio_files` table

---

## Key Constraints

- No Docker until Sprint 7 — Sprint 6 uses a local PostgreSQL instance
- No breaking changes to Sprint 1–5 packages
- `SQLAlchemy` and `alembic` added to `requirements-dev.txt`
- `asyncpg` driver for async support (Sprint 7 FastAPI will need async)

---

## Files to Create in Sprint 6

```
database/
├── __init__.py
├── base.py              # Declarative Base
├── session.py           # Engine + session factory
├── models/
│   ├── __init__.py
│   ├── project.py       # Project table
│   ├── daily_log.py     # DailyLog table (core Sprint 4 output)
│   ├── audio_file.py    # AudioFile table (Sprint 3 metadata)
│   └── generation.py    # GenerationOutput table (Sprint 5 outputs)
└── migrations/
    ├── env.py
    ├── script.py.mako
    └── versions/
        └── 0001_initial_schema.py

scripts/
└── seed_database.py     # Insert sample data

docs/
└── DATABASE.md          # ER diagram + schema reference
```

---

## Definition of Done (Sprint 6)

- [ ] PostgreSQL schema covers all 12 ConstructionDailyLog sections
- [ ] ORM models created for all tables with relationships
- [ ] `alembic upgrade head` runs without errors on a fresh database
- [ ] `alembic downgrade base` reverses all migrations cleanly
- [ ] Seed script inserts 5 valid sample records
- [ ] ER diagram documented in `docs/DATABASE.md`
- [ ] Integration: `ExtractionResult` can be saved and reloaded via ORM
- [ ] Integration: `GenerationResult` can be saved and reloaded via ORM
- [ ] All Sprint 1–5 tests continue to pass
- [ ] New Sprint 6 tests achieve >80% coverage on ORM models
- [ ] Sprint Review generated + owner approval obtained before Sprint 7
