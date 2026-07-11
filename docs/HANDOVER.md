# HANDOVER — Construction Site AI

**Purpose:** This document allows any future developer or AI-assisted session to immediately understand the project state, architecture, and next steps without reading the entire conversation history.

**Last Updated:** 2026-07-11
**Handover Status:** Sprint 7 COMPLETE — Awaiting Owner Approval for Sprint 8

---

## 1. What This Project Is

**Construction Site AI** is a production-grade AI SaaS application that converts foreman voice recordings into 5 outputs:

1. Structured daily site log (JSON)
2. Customer-facing progress update (email)
3. Safety toolbox talk (formatted content)
4. Material reminder (shopping/order list)
5. Structured database records (PostgreSQL)

**Target users:** Residential general contractors in the USA.
**Problem solved:** Foremen spend 30–60 minutes daily on paperwork. This product turns that into a 2-minute voice note.

---

## 2. Critical Project Constraints

These constraints are NON-NEGOTIABLE and must be respected in every sprint:

```
CONSTRAINT: Use ONLY FREE technologies.
- NO paid APIs (no OpenAI API, no Anthropic API, no Gemini, no Azure AI, no AWS AI)
- NO paid SaaS (no Twilio, no third-party paid services)
- Everything runs locally
- Always prefer Open Source
```

```
CONSTRAINT: Never continue to the next sprint automatically.
- At the end of every sprint: STOP
- Generate a Sprint Review
- Wait for explicit owner approval before proceeding
```

```
CONSTRAINT: Never create files or folders for future sprints.
- No placeholder code
- No dummy implementations
- Only create what the current sprint requires
```

---

## 3. Current Sprint Status

| Field | Value |
|-------|-------|
| Sprint 1 Status | APPROVED & FROZEN |
| Sprint 2 Status | APPROVED & FROZEN |
| Sprint 3 Status | APPROVED & FROZEN |
| Sprint 4 Status | APPROVED & FROZEN |
| Sprint 5 Status | APPROVED & FROZEN |
| Sprint 5.0 Scope | AI Generation Service Layer (AIServiceManager, 4 services, Pydantic models, content validation) |
| Sprint 5.1 Scope | Hardening: mtime cache, PromptRegistry, ServiceRegistry, generation_id, observability layer |
| Sprint 6 Status | APPROVED & FROZEN |
| Sprint 6 Scope | Production database layer: 26 SQLAlchemy models, 9 repositories, Alembic migration, 2 seed scripts, 123 tests |
| Sprint 7 Status | COMPLETE — PENDING APPROVAL |
| Sprint 7 Scope | Production FastAPI backend (`app/`): JWT auth, 4 health endpoints, audio upload + background pipeline, daily-log review lifecycle, AI generation trigger, standardized response envelope, 31 API tests |
| Next Sprint | Sprint 8 — Auth hardening + Celery/Redis task queue |
| Schema Version | ConstructionDailyLog v1.0.0 (FROZEN) |

**Sprint 7 is COMPLETE.** Production FastAPI backend built: application factory pattern, `/api/v1` versioned routing, JWT auth (login only — no registration/reset, per scope), standardized response envelope on every endpoint, centralized exception handling, structured request logging, 4 distinct health endpoints (`/health`, `/live`, `/ready`, `/version`), audio upload with background-task pipeline orchestration (speech → extraction → DB → generation → DB, Celery-ready), and daily-log review lifecycle delegating entirely to the frozen Sprint 6 repository state machine.
Full test suite: 777 passed, 1 skipped, zero regressions. Live-verified over real HTTP against real PostgreSQL and real Groq.
Sprint 8 (Auth hardening + Celery/Redis) is next — see `docs/NEXT_SPRINT.md`.

---

## 4. Repository Structure

```
Construction-Site-AI/
│
├── knowledge/                                   FROZEN (Sprint 1)
│   ├── construction_stages.json                 11 stages, full detail
│   ├── construction_daily_log_schema.json        Master schema v1.0.0
│   ├── construction_rules.json                  38 sequencing/validation rules
│   ├── dependency_graph.json                    DAG: 23 nodes, 33 edges
│   ├── validation_rules.json                    35 machine-readable validators
│   └── construction_ontology.json               Entity-relationship ontology
│
├── docs/
│   ├── sprint_1/                                FROZEN (Sprint 1)
│   │   ├── CONSTRUCTION_RESEARCH.md
│   │   └── SCHEMA_DESIGN.md
│   ├── CHANGELOG.md
│   ├── DECISIONS.md                             Architecture decision records
│   ├── PROJECT_STATE.md                         Evolving state (not the frozen root one)
│   ├── NEXT_SPRINT.md                           Sprint 8 spec
│   ├── ROADMAP.md                               Full product roadmap
│   └── HANDOVER.md                              This file
│
├── README.md
├── .gitignore
├── .env.example
└── PROJECT_STATE.md                             FROZEN Sprint 1 root artifact
```

**Created in Sprint 2:**
- `dataset_generation_framework/` — Full pipeline (config, core, generators, validation, exporters, statistics)
- `datasets/` — raw/, generated/, validated/, exports/ directories
- `tests/` — 5 test modules (unit + integration)
- `generate.py` — CLI entry point
- `requirements-dev.txt` — Dev dependencies

**Created in Sprint 3:**
- `speech/` — Engine-agnostic Speech Processing Framework (config, models, loaders, validators, preprocessors, whisper engine, postprocessors, metadata, exporters). See `docs/SPEECH_PIPELINE.md`.
- `transcribe.py` — CLI entry point for transcription
- `scripts/create_sample_audio.py` — Synthetic audio fixture generator
- `data/sample_audio/`, `data/transcripts/{raw,cleaned}/` — Sample audio + transcript output directories
- `tests/conftest.py` + 5 new `tests/test_speech_*.py` / `test_audio_pipeline.py` modules
- `docs/AI_PIPELINE.md`, `docs/SPEECH_PIPELINE.md`

**Created in Sprint 4:**
- `extraction/` — Provider-agnostic AI Extraction Framework (config, models, engines, prompts, validators, postprocessors). `BaseLLMProvider` + `GroqEngine` + `EngineFactory`.
- `extract.py` — CLI entry point for extraction
- `tests/test_extraction_models.py`, `test_extraction_config.py`, `test_json_repairer.py`, `test_extraction_pipeline.py`

**Created in Sprint 5.0:**
- `generation/` — AI Generation Service Layer: `AIServiceManager`, 4 typed services, Pydantic output models, versioned `.md` prompts, `ContentValidator`, `PromptLoader`
- `report.py` — CLI entry point for generation
- `data/generated/` — Runtime output directory (git-ignored, `.gitkeep` tracked)
- `tests/test_generation_models.py`, `test_generation_config.py`, `test_generation_prompts.py`, `test_content_validator.py`, `test_generation_services.py`, `test_generation_manager.py` (164 tests)
- `docs/AI_SERVICES.md` — Complete generation framework reference

**Created in Sprint 5.1 (Hardening):**
- `generation/prompts/registry.py` — `PromptRegistry` + `DEFAULT_PROMPT_REGISTRY` (4 built-in prompts)
- `generation/services/registry.py` — `ServiceRegistry` + `DEFAULT_SERVICE_REGISTRY` (4 built-in services)
- `generation/observability/__init__.py`, `events.py`, `timers.py`, `metrics.py` — In-process observability layer
- `tests/test_prompt_cache.py`, `test_prompt_registry.py`, `test_service_registry.py`, `test_observability.py` (109 new tests)
- **Modified:** `generation/prompts/loader.py` (mtime cache), `generation/services/base_service.py` (observability events, remove dual-cache), `generation/manager.py` (ServiceRegistry DI), `generation/models/outputs.py` (generation_id)

**Created in Sprint 6:**
- `database/` — Production persistence layer: 26 SQLAlchemy 2.x ORM models, 9 typed repository classes, Alembic initial migration, 2 idempotent seed scripts, 123 tests (SQLite in-memory). See `docs/DATABASE_ARCHITECTURE.md`.
- `alembic.ini` — Alembic configuration
- `database/migrations/` — Migration scripts (Alembic)
- `verify_sprint6.py` — End-to-end pipeline verification script

**Created in Sprint 7:**
- `app/` — Production FastAPI backend: application factory, `/api/v1` versioned routing, JWT auth, standardized response envelope, centralized exception handling, structured logging, background-task pipeline orchestration. See `docs/BACKEND_ARCHITECTURE.md`.
- `pytest.ini` — pytest-asyncio configuration
- `tests/test_api_*.py`, `test_db_async_session.py`, `test_core_security.py`, `test_app_dev_seed.py` — 59 new tests
- `docs/BACKEND_ARCHITECTURE.md`, `docs/BACKEND_STARTUP.md`, `docs/CONTRIBUTING.md`

**NOT YET CREATED (future sprints):**
- `frontend/` — Sprint 9+

---

## 5. Architecture Status

### AI Stack

| Component | Technology | Purpose | Sprint | Status |
|-----------|-----------|---------|--------|--------|
| Speech-to-text | Faster Whisper (local), via `speech/whisper/engine.py` | Audio → transcript | Sprint 3 | ✅ Done |
| Language model (extraction) | Groq API (llama-3.3-70b-versatile), via `extraction/engines/groq_engine.py` | Transcript → ConstructionDailyLog | Sprint 4 | ✅ Framework done |
| Language model (generation) | Groq API (free tier) | Log → customer email / report / safety talk | Sprint 5 | ✅ Done |
| Vector store | FAISS (local) | RAG from knowledge base | Future | Planned |

### Backend Stack

| Component | Technology | Sprint | Status |
|-----------|-----------|--------|--------|
| ORM | SQLAlchemy 2.x | Sprint 6 | ✅ Done |
| Database | PostgreSQL 15 | Sprint 6 | ✅ Done |
| Migrations | Alembic | Sprint 6 | ✅ Done |
| API framework | FastAPI | Sprint 7 | ✅ Done |
| Authentication | JWT (login only) | Sprint 7 | ✅ Done — registration/reset/full role enforcement in Sprint 8 |
| Task queue | FastAPI BackgroundTasks | Sprint 7 | ✅ Done — Celery + Redis migration planned Sprint 8 (extension point documented in `docs/BACKEND_ARCHITECTURE.md` §10) |

### Frontend (Planned)
- React + TypeScript — Sprint 9

---

## 6. Knowledge Base Status

All 6 knowledge files are FROZEN. Do not modify them unless the owner explicitly requests a schema change.

### `construction_stages.json`
11 stages: site_preparation, foundation, concrete_flatwork, framing, roofing, electrical_rough_in, hvac_rough_in, plumbing_rough_in, insulation, drywall, painting, electrical_finish, hvac_finish, plumbing_finish, flooring, trim_and_millwork, cabinets_and_countertops, tile_work, final_cleanup, inspection, punch_list, project_closeout

Each stage has: workers (with licenses), materials (with units), tools, duration, hazards (OSHA refs), inspection points, weather sensitivity, daily report fields.

### `construction_daily_log_schema.json`
JSON Schema draft-07. 12 sections. 80+ fields. UUID v4 keys. Explicit `["type", "null"]` for optionals.

**22-value `current_stage` enum** (important: schema uses 22 values, not 11 like the knowledge base stages)

**Required fields:** log_id, schema_version, log_date, log_source, project.project_id, current_stage, workforce.total_workers_present, work_completed

### `construction_rules.json`
38 rules with rule_id, severity, category, prerequisite_stage, dependent_stage, lag_days.
- Fatal rules prevent logically impossible sequences
- Error rules catch likely mistakes
- Warning rules flag unusual but possible scenarios
- Info rules provide advisory context

### `dependency_graph.json`
Full DAG. Critical path: 97 days (foundation → framing → electrical_rough_in → insulation → drywall → painting → cabinets → punch_list → inspection → closeout). 3 parallel groups. Includes topological sort.

### `validation_rules.json`
35 rules. Categories: SEQ, MAT, WRK, WTH, QTY, DTE, INS, SAF, FIN.
- Phase 1 (blocking): Must pass before any write
- Phase 2 (non_blocking_error): Log error, allow write with flag
- Phase 3 (warning): Advisory
- Phase 4 (info): Metadata

Consumed by: Sprint 2 generators, Sprint 4 AI validator, Sprint 7 API input validation.

### `construction_ontology.json`
Entities: 14 trades, 16 materials, 6 equipment types, 10 hazards, 8 PPE types, 5 worker roles, 7 inspection types, 6 delay types, 6 weather conditions. 40+ relationships. Designed for future RAG/FAISS embedding.

---

## 7. Schema Version Details

**Version:** ConstructionDailyLog v1.0.0
**$id:** `https://constructionsite.ai/schemas/construction_daily_log/v1.0.0`
**Format:** JSON Schema draft-07

**Key design decisions (see DECISIONS.md for full rationale):**
- UUID v4 for all IDs — security + distributed generation
- Explicit null typing — distinguish AI-null from missing field
- 22-value stage enum — more granular than 11 research stages
- 12 sections — mirrors planned database table structure
- AI outputs stored in the log itself — simplifies retrieval

**If schema changes are needed:** Bump to v1.1.0, update CHANGELOG.md, regenerate Pydantic models (Sprint 4+).

---

## 8. Sprint Summary (Sprints 1–7) / Sprint 8 (What's Next)

**Sprint 3 — Speech Processing Framework (FROZEN):**
- `speech/` package: `BaseSTTEngine` abstraction, `FasterWhisperEngine` as the
  sole implementation, lazy model loading, 7-stage pipeline
- `SpeechProcessingResult` — structured, never plain text, never raises for expected failure modes
- Full spec: `docs/SPEECH_PIPELINE.md`

**Sprint 4 — AI Information Extraction (FROZEN):**
- `extraction/` package: `BaseLLMProvider` interface, `GroqEngine` as the sole
  implementation (Groq cloud API via `groq` package), `EngineFactory` registry
  for provider-agnostic engine creation, prompt builder with schema-derived enum
  context, 3-strategy JSON repair, two-stage validation
  (JSON Schema + Sprint 2 `ValidationPipeline`)
- `ExtractionResult` — structured, fully serializable, with field confidences
- `extract.py` CLI
- 66 tests, all passing with `MockExtractionEngine` (no API key needed for unit tests)

**Sprint 5 — AI Generation Services (FROZEN):**
- `generation/` package: `AIServiceManager`, 4 typed services (`DailyReportService`,
  `CustomerUpdateService`, `SafetyTalkService`, `MaterialReminderService`), Pydantic
  output models, versioned `.md` prompts, `ContentValidator`, `PromptLoader`,
  `PromptRegistry`, `ServiceRegistry`, observability layer
- `GenerationResult` — aggregated Pydantic model with 4 named output fields
- 273 tests (164 Sprint 5.0 + 109 Sprint 5.1), all passing

**Sprint 6 — Database Persistence Layer (FROZEN):**
- `database/` package: 26 SQLAlchemy 2.x ORM models (Mapped[T] style), 9 typed
  repository classes, Alembic initial migration, 2 idempotent seed scripts
- 123 tests (SQLite in-memory, no PostgreSQL required for CI)
- See `docs/DATABASE_ARCHITECTURE.md`

**Sprint 7 — Production FastAPI Backend (COMPLETE — PENDING APPROVAL):**
- `app/` package: application factory, `/api/v1` versioned routing, JWT auth
  (login only), standardized response envelope on every endpoint, centralized
  exception handling, structured request logging, 4 health endpoints
  (`/health`, `/live`, `/ready`, `/version`)
- Audio upload with `BackgroundTasks` pipeline orchestration (speech →
  extraction → DB → generation → DB), Celery-ready extension point
- Daily-log review lifecycle delegating entirely to the frozen Sprint 6
  `DailyLogRepository` state machine
- `database.session.get_async_session()` added (additive) — repository
  layer intentionally stays sync (see ADR-031)
- 59 new tests (`test_api_*`, `test_db_async_session`, `test_core_security`,
  `test_app_dev_seed`); full suite 777 passed, 1 skipped, zero regressions
- Live-verified over real HTTP against real PostgreSQL and real Groq
- Two real bugs caught during manual verification and fixed — see
  `docs/CHANGELOG.md` [Sprint 7] "Fixed" section
- See `docs/BACKEND_ARCHITECTURE.md`, `docs/BACKEND_STARTUP.md`,
  `docs/CONTRIBUTING.md`

**Sprint 8 — Auth Hardening + Celery/Redis (next):**
Full spec in `docs/NEXT_SPRINT.md`. Core: user registration, password reset,
full role-based access enforcement, Celery + Redis replacing
`BackgroundTasks` for the pipeline (migration path already documented in
`docs/BACKEND_ARCHITECTURE.md` §10).

---

## 9. Sprint Roadmap (Full)

| Sprint | Phase | Goal | Status |
|--------|-------|------|--------|
| 1 | Core AI Pipeline | Knowledge base + Schema | ✅ APPROVED & FROZEN |
| 2 | Core AI Pipeline | Synthetic datasets | ✅ APPROVED & FROZEN |
| 3 | Core AI Pipeline | Faster Whisper STT | ✅ APPROVED & FROZEN |
| 4 | Core AI Pipeline | AI extraction (Groq / llama-3.3-70b-versatile) | ✅ APPROVED & FROZEN |
| 5 | Core AI Pipeline | AI generation services (4 outputs) | ✅ APPROVED & FROZEN |
| 6 | Core AI Pipeline | PostgreSQL schema + Alembic | ✅ APPROVED & FROZEN |
| 7 | Backend API | FastAPI backend (JWT login, health, audio, daily-logs, generation) | ✅ COMPLETE — PENDING APPROVAL |
| 8 | Backend API | Auth hardening + Celery/Redis + multi-tenancy enforcement | Not started |
| 9 | Frontend | React frontend core | Not started |
| 10 | Frontend | Reports + client portal | Not started |
| 11–14 | Intelligence | Scheduling, inventory, analytics, cost | Not started |
| Future | Advanced AI | Computer vision, bid estimation, multilingual | Not started |

---

## 10. Known Issues

| Issue | Severity | Status |
|-------|----------|--------|
| Schema is English-only | Medium | Deferred to future sprint |
| USA-centric standards (OSHA, IRC, NFPA) | Low | Documented, international in roadmap |
| Python validation tooling | Resolved | Built in Sprint 4 — `SchemaValidator` in `extraction/validators/schema_validator.py` |
| Weather auto-fetch not designed | Low | Deferred to future sprint |
| 11-stage research vs 22-stage schema (noted gap) | Resolved | Covered by ADR-008, ontology, dependency graph |

---

## 11. Important Engineering Notes

These notes are non-obvious and critical for future sessions:

**1. The schema enum has 22 values, the knowledge base documents 11 stages.**
This is intentional (ADR-008). The 11 stages are broad conceptual groupings. The 22 enum values are the granular sub-stages that foresmen actually report. Dataset generators must use the 22 enum values.

**2. Null vs Missing in the schema (ADR-003).**
Optional fields must be set to `null` (not omitted) when the AI extraction engine finds no value. Missing means "field didn't exist at creation time." Null means "AI processed, found nothing." This distinction matters for migration and audit.

**3. All knowledge files load into memory at module startup.**
Sprint 2 generators will open JSON files from `knowledge/` directory using relative paths. The design assumes generators run from the project root.

**4. Validation rules have phased execution.**
Phase 1 (blocking) → Phase 2 (non_blocking_error) → Phase 3 (warning) → Phase 4 (info). A blocking failure should abort the write. A non_blocking_error should flag the record but allow it. Never skip Phase 1.

**5. Critical path is 97 days.**
When generating project schedules in Sprint 2, the minimum realistic project duration from this codebase's dependency graph is 97 days. Use this as the baseline; add realistic variance.

**6. Root PROJECT_STATE.md is frozen.**
The file at the root (`PROJECT_STATE.md`) is a Sprint 1 frozen artifact. The canonical evolving state is at `docs/PROJECT_STATE.md`. Do not modify the root one.

**7. No Docker yet.**
Sprint 2 and Sprint 3 are pure Python (Sprint 3 adds Faster Whisper, run locally via the `faster-whisper`/CTranslate2 package — no Docker needed for STT). Sprint 4 uses the Groq cloud API (free tier, `groq` pip package, key in `.env`). Sprint 7 shipped the FastAPI backend running via plain `uvicorn` — still no Docker. Production Docker deployment is explicitly out of scope until Sprint 10 (see `docs/NEXT_SPRINT.md`'s historical Sprint 7 spec). Never add Docker configuration to a sprint that doesn't require it.

**8. Engine abstraction precedent (Sprint 3).**
`speech/whisper/engine.py` is the only file that imports `faster_whisper`; `extraction/engines/groq_engine.py` is the only file that imports `groq`. Every other file talks to the abstract interface (`BaseSTTEngine`, `BaseLLMProvider`). Future providers follow the same pattern: one engine file, registered via `EngineFactory`.

---

## 12. File Loading Order (For Sprint 2 Generators)

When writing generators, load knowledge files in this order:

```python
knowledge/construction_daily_log_schema.json  # Target schema for validation
knowledge/construction_stages.json            # Worker counts, material lists
knowledge/dependency_graph.json               # Stage sequencing state machine
knowledge/construction_rules.json            # Rule enforcement
knowledge/validation_rules.json              # Output validation
knowledge/construction_ontology.json         # Entity relationships
```

---

## 13. Environment Setup (Current — Sprint 1-4)

```bash
# Python 3.12 required
python --version

# Install all dependencies (Sprint 2 + Sprint 3 + Sprint 4)
pip install -r requirements-dev.txt

# Sprint 4 requires a Groq API key for real extractions (free at console.groq.com)
cp .env.example .env
# Edit .env — set GROQ_API_KEY=gsk_your_actual_key_here

# Run the full test suite (unit tests run without an API key)
pytest tests/ -v
```

No Docker. No virtual environment required (though recommended).
Sprint 4's extraction framework requires `GROQ_API_KEY` in `.env` for real
LLM calls. Unit tests inject `MockExtractionEngine` and run fully without it.
Speech framework downloads Faster Whisper model weights on first real
transcription call, not at install time.
