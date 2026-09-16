# PROJECT STATE — Construction Site AI

**Primary project state document. Updated at end of every sprint.**
**Note:** The root-level `PROJECT_STATE.md` is a frozen Sprint 1 artifact. This file is the evolving, canonical state.

---

## Current Status

| Field | Value |
|-------|-------|
| Current Sprint | Sprint 14 — Cost Intelligence (spec written, implementation not yet started) |
| Next Sprint | Sprint 15+ (per `docs/ROADMAP.md`'s Phase 4+) |
| Sprint 1 Status | APPROVED & FROZEN |
| Sprint 2 Status | APPROVED & FROZEN |
| Sprint 3 Status | APPROVED & FROZEN |
| Sprint 4 Status | APPROVED & FROZEN |
| Sprint 5 Status | APPROVED & FROZEN |
| Sprint 6 Status | APPROVED & FROZEN |
| Sprint 7 Status | APPROVED & FROZEN |
| Sprint 8 Status | APPROVED & FROZEN (approved 2026-08-19, after the post-Sprint-8 fixes were verified — see "Post-Sprint-8 Work") |
| Sprint 9 Status | APPROVED & FROZEN (approved 2026-08-19) |
| Sprint 10 Status | APPROVED & FROZEN (approved 2026-09-15, after independent live re-verification during the resume audit — see `docs/RESUME_AUDIT_2026-09-15.md`) |
| Sprint 11 Status | APPROVED & FROZEN (approved 2026-09-16, after the post-resume-audit P1/P2 backlog cleanup was verified live — 1042 backend + 86 frontend tests passing) |
| Sprint 12 Status | APPROVED & FROZEN (approved 2026-09-16, all 7 deliverables verified live — 1067 backend + 97 frontend tests passing) |
| Sprint 13 Status | **APPROVED & FROZEN** (approved 2026-09-16, all 7 deliverables verified live — 1081 backend + 116 frontend tests passing) |
| Last Updated | 2026-09-16 |
| Schema Version | ConstructionDailyLog v1.0.0 |
| Codebase | Knowledge base + Data generation + Speech + AI Extraction + AI Generation + Production database layer + Production FastAPI backend + Authentication/Authorization layer + Sprint 9 (task queue, email, RedisRateLimiter, React frontend core) + Sprint 10 (reports and client portal) + Sprint 11 (scheduling module) + Sprint 12 (inventory and procurement) + **Sprint 13: `GET /projects/{id}/analytics` extended with schedule projections, delay-by-trade, safety incident trends, productivity by stage/trade, and client-role curation — no new tables** |
| Database | 32 tables (+ `alembic_version`), migrations `001`–`006` (unchanged since Sprint 12 — Sprint 13 added no schema) |
| New infrastructure (Sprint 12) | None — no new services; inventory/lead-time computation is pure Python (`app/services/inventory_service.py`), no AI/LLM calls (ADR-048's posture, applied here too) |

---

## Repository Structure (Current State)

```
Construction-Site-AI/
│
├── knowledge/                              SPRINT 1 — FROZEN
│   ├── construction_stages.json           ✅ 11 stages, full detail
│   ├── construction_daily_log_schema.json ✅ Master schema v1.0.0
│   ├── construction_rules.json            ✅ 38 rules (new in Sprint 1.1)
│   ├── dependency_graph.json              ✅ 23 nodes, 33 edges (new)
│   ├── validation_rules.json              ✅ 35 rules (new)
│   └── construction_ontology.json         ✅ Entity-relationship ontology (new)
│
├── docs/
│   ├── sprint_1/                          SPRINT 1 — FROZEN
│   │   ├── CONSTRUCTION_RESEARCH.md       ✅ Human-readable domain research
│   │   └── SCHEMA_DESIGN.md              ✅ Schema architecture decisions
│   │
│   ├── CHANGELOG.md                       ✅ Sprint 1.1 (new)
│   ├── DECISIONS.md                       ✅ Architecture decision record (new)
│   ├── PROJECT_STATE.md                   ✅ This file (new)
│   ├── NEXT_SPRINT.md                     ✅ Sprint 13 spec (updated each sprint)
│   ├── ROADMAP.md                         ✅ Full product roadmap (new)
│   └── HANDOVER.md                        ✅ Handover document (new)
│
├── README.md                              ✅ Sprint 1
├── .gitignore                             ✅ Sprint 1
├── .env.example                           ✅ Sprint 1
└── PROJECT_STATE.md                       ✅ Sprint 1 (FROZEN root artifact)

├── dataset_generation_framework/              ✅ SPRINT 2 — NEW
│   ├── __init__.py                           ✅ v1.0.0
│   ├── config.py                             ✅ All scale/config constants
│   ├── core/
│   │   ├── knowledge_loader.py               ✅ KnowledgeBase singleton + O(1) indexes
│   │   ├── stage_machine.py                  ✅ DAG-based ProjectState + StageMachine
│   │   └── rule_engine.py                    ✅ construction_rules.json query API
│   ├── generators/
│   │   ├── base_generator.py                 ✅ Abstract streaming BaseGenerator
│   │   ├── daily_log_generator.py            ✅ Full project simulation → DailyLog
│   │   ├── schedule_generator.py             ✅ Planned vs. actual schedules
│   │   ├── safety_talk_generator.py          ✅ OSHA-based safety talks (CSV)
│   │   ├── material_generator.py             ✅ Material catalog (CSV)
│   │   └── customer_update_generator.py      ✅ (raw notes, email) training pairs
│   ├── validation/
│   │   └── pipeline.py                       ✅ 4-phase ValidationPipeline
│   ├── exporters/
│   │   ├── jsonl_exporter.py                 ✅ Batched JSONL writer
│   │   └── csv_exporter.py                   ✅ Batched CSV writer
│   └── statistics/
│       └── report_generator.py               ✅ Post-generation stats report
│
├── datasets/                                  ✅ SPRINT 2 — NEW
│   ├── README.md                             ✅ Dataset documentation
│   ├── raw/                                  (staging area)
│   ├── generated/                            (all generated records)
│   ├── validated/                            (validation-passed records)
│   └── exports/                              (final consumer-ready files)
│
├── tests/                                     ✅ SPRINT 2 — NEW
│   ├── test_knowledge_loader.py              ✅ Unit tests
│   ├── test_stage_machine.py                 ✅ Unit tests
│   ├── test_validation_pipeline.py           ✅ Unit tests
│   ├── test_generators.py                    ✅ Unit tests (all 5 generators)
│   └── test_integration.py                   ✅ End-to-end pipeline tests
│
├── generate.py                                ✅ SPRINT 2 — CLI entry point
├── requirements-dev.txt                       ✅ SPRINT 2/3 — Dev dependencies
│
├── speech/                                    ✅ SPRINT 3 — NEW
│   ├── __init__.py                           ✅ Public API: SpeechProcessingPipeline
│   ├── config.py                             ✅ SpeechProcessingConfig (+ from_env())
│   ├── pipeline.py                           ✅ SpeechProcessingPipeline orchestrator
│   ├── utils/
│   │   ├── constants.py                      ✅ Formats, limits, filler words
│   │   └── retry.py                          ✅ Exponential backoff @retry decorator
│   ├── models/
│   │   ├── transcript.py                     ✅ Transcript, TranscriptSegment, WordTimestamp
│   │   ├── metadata.py                       ✅ SpeechProcessingMetadata, ProcessingStats
│   │   └── processing_result.py              ✅ SpeechProcessingResult, AudioValidationResult
│   ├── loaders/
│   │   ├── format_detector.py                ✅ Extension + magic-byte format detection
│   │   └── audio_loader.py                   ✅ soundfile/librosa metadata extraction
│   ├── validators/
│   │   └── audio_validator.py                ✅ 8 blocking checks + 3 warnings
│   ├── preprocessors/
│   │   ├── audio_normalizer.py               ✅ Peak normalization to -3 dBFS
│   │   ├── noise_reducer.py                  ✅ Optional noisereduce wrapper
│   │   └── chunker.py                        ✅ AudioChunker boundary calculation
│   ├── whisper/
│   │   └── engine.py                         ✅ BaseSTTEngine + FasterWhisperEngine (sole faster_whisper import)
│   ├── postprocessors/
│   │   ├── construction_normalizer.py        ✅ Pattern-based term correction
│   │   └── transcript_cleaner.py             ✅ TranscriptCleaner
│   ├── metadata/
│   │   └── extractor.py                      ✅ MetadataExtractor
│   └── exporters/
│       ├── base_exporter.py                  ✅ BaseExporter interface
│       ├── json_exporter.py                  ✅ JSONExporter, JSONLExporter
│       └── text_exporter.py                  ✅ TextExporter, VerboseTextExporter
│
├── transcribe.py                              ✅ SPRINT 3 — CLI entry point
├── scripts/
│   └── create_sample_audio.py                ✅ SPRINT 3 — Synthetic WAV fixture generator
│
├── data/                                      ✅ SPRINT 3 — NEW; Sprint 4 expanded
│   ├── sample_audio/                         ✅ 10 synthetic WAVs + ground-truth .txt + README
│   ├── transcripts/
│   │   ├── raw/                              (gitkept, CLI output, gitignored content)
│   │   └── cleaned/                          (gitkept, CLI output, gitignored content)
│   ├── extracted/                            ✅ SPRINT 4 — NEW (gitkept, CLI output, gitignored)
│   └── generated/                            ✅ SPRINT 5 — NEW (gitkept, CLI output, gitignored)
│
├── tests/ (Sprint 3 additions)                ✅ SPRINT 3 — NEW
│   ├── conftest.py                           ✅ Synthetic WAV fixtures
│   ├── test_speech_models.py                 ✅ Data model + serialization tests
│   ├── test_speech_config.py                 ✅ Config + from_env() tests
│   ├── test_speech_validator.py              ✅ All 8 checks + 3 warnings
│   ├── test_transcript_cleaner.py            ✅ Filler/hallucination/normalization tests
│   └── test_audio_pipeline.py                ✅ Full pipeline integration (MockSTTEngine)
│
├── extraction/                                ✅ SPRINT 4 — NEW
│   ├── __init__.py                           ✅ Public API: ExtractionPipeline, ExtractionConfig, GroqConfig
│   ├── config.py                             ✅ ExtractionConfig + GroqConfig (from_env())
│   ├── pipeline.py                           ✅ ExtractionPipeline orchestrator
│   ├── models/
│   │   └── extraction_result.py              ✅ ExtractionResult, ExtractionMetadata
│   ├── engines/
│   │   ├── __init__.py                       ✅ Exports BaseLLMProvider, EngineFactory (no concrete engines)
│   │   ├── base_engine.py                    ✅ BaseLLMProvider (abstract interface)
│   │   ├── factory.py                        ✅ EngineFactory — registry-based provider-agnostic factory
│   │   └── groq_engine.py                    ✅ GroqEngine — sole Groq API caller (sole groq import)
│   ├── prompts/
│   │   ├── system_prompt.txt                 ✅ LLM system instructions
│   │   └── builder.py                        ✅ PromptBuilder with schema context
│   ├── validators/
│   │   └── schema_validator.py               ✅ JSON Schema + Sprint 2 business rules
│   └── postprocessors/
│       └── json_repairer.py                  ✅ repair_json() — 3-strategy JSON extraction
│
├── extract.py                                 ✅ SPRINT 4 — CLI entry point
│
├── tests/ (Sprint 4 additions)
│   ├── test_extraction_models.py             ✅ ExtractionResult + metadata tests
│   ├── test_extraction_config.py             ✅ Config + from_env() tests
│   ├── test_json_repairer.py                 ✅ JSON repair strategy tests
│   └── test_extraction_pipeline.py           ✅ Full pipeline integration (MockExtractionEngine)
│
├── generation/                                ✅ SPRINT 5.0 — NEW; Sprint 5.1 expanded
│   ├── __init__.py                           ✅ Public API: AIServiceManager, all output types
│   ├── config.py                             ✅ GenerationConfig + GenerationGroqConfig (from_env())
│   ├── manager.py                            ✅ AIServiceManager — uses ServiceRegistry (Sprint 5.1)
│   ├── models/
│   │   └── outputs.py                        ✅ Pydantic: ServiceType, ServiceMetadata (+generation_id), ServiceOutput, GenerationResult
│   ├── prompts/
│   │   ├── loader.py                         ✅ PromptLoader — mtime-aware cache (Sprint 5.1); versioned .md + frontmatter
│   │   ├── registry.py                       ✅ SPRINT 5.1 — PromptRegistry + DEFAULT_PROMPT_REGISTRY
│   │   ├── daily_report.md                   ✅ v1.0.0 formal contractor report prompt
│   │   ├── customer_update.md                ✅ v1.0.0 client-facing email prompt
│   │   ├── safety_talk.md                    ✅ v1.0.0 OSHA-referenced safety briefing prompt
│   │   └── material_reminder.md              ✅ v1.0.0 procurement reminder prompt
│   ├── services/
│   │   ├── base_service.py                   ✅ BaseAIService (Template Method + observability events, Sprint 5.1)
│   │   ├── registry.py                       ✅ SPRINT 5.1 — ServiceRegistry + DEFAULT_SERVICE_REGISTRY
│   │   ├── daily_report.py                   ✅ DailyReportService
│   │   ├── customer_update.py                ✅ CustomerUpdateService
│   │   ├── safety_talk.py                    ✅ SafetyTalkService
│   │   └── material_reminder.py              ✅ MaterialReminderService
│   ├── validators/
│   │   └── content_validator.py              ✅ ContentValidator — 6 AI output quality checks
│   └── observability/                         ✅ SPRINT 5.1 — NEW
│       ├── __init__.py                        ✅ Public: METRICS, GenerationMetrics, Timer
│       ├── events.py                          ✅ 9 typed frozen event dataclasses
│       ├── timers.py                          ✅ Timer context manager
│       └── metrics.py                         ✅ GenerationMetrics accumulator + METRICS global
│
├── report.py                                  ✅ SPRINT 5.0 — CLI entry point
│
├── tests/ (Sprint 5.0 + 5.1 additions)
│   ├── test_generation_models.py             ✅ 32 Pydantic output model tests (incl. generation_id)
│   ├── test_generation_config.py             ✅ 14 config + env override tests
│   ├── test_generation_prompts.py            ✅ 22 prompt loader + frontmatter tests
│   ├── test_content_validator.py             ✅ 23 content validation tests
│   ├── test_generation_services.py           ✅ 26 service + retry + cache tests
│   ├── test_generation_manager.py            ✅ 19 orchestration + DI tests
│   ├── test_prompt_cache.py                  ✅ SPRINT 5.1 — 12 mtime cache tests
│   ├── test_prompt_registry.py               ✅ SPRINT 5.1 — 23 PromptRegistry tests
│   ├── test_service_registry.py              ✅ SPRINT 5.1 — 24 ServiceRegistry tests
│   └── test_observability.py                 ✅ SPRINT 5.1 — 48 Timer + events + metrics tests
│
├── docs/AI_PIPELINE.md                        ✅ SPRINT 3 — Full app AI pipeline reference
├── docs/SPEECH_PIPELINE.md                    ✅ SPRINT 3 — Speech framework reference
├── docs/AI_SERVICES.md                        ✅ SPRINT 5 — Generation framework reference
│
├── database/                                  ✅ SPRINT 6 — NEW
│   ├── __init__.py                           ✅ Re-exports Base, DatabaseConfig, get_session
│   ├── base.py                               ✅ DeclarativeBase — shared by all 26 models
│   ├── config.py                             ✅ DatabaseConfig + from_env() + for_testing()
│   ├── mixins.py                             ✅ 4 mixins: UUID PK, Timestamp, SoftDelete, AuditUser
│   ├── session.py                            ✅ get_engine() singleton, get_session() context manager
│   ├── models/
│   │   ├── __init__.py                       ✅ Imports all 26 models (critical for Alembic)
│   │   ├── reference.py                      ✅ Trade, ConstructionStage, MaterialCategory, PPEType
│   │   ├── company.py                        ✅ Company, User
│   │   ├── project.py                        ✅ Project, Site, ProjectWorker
│   │   ├── worker.py                         ✅ Worker
│   │   ├── audio.py                          ✅ AudioFile, SpeechTranscript
│   │   ├── daily_log.py                      ✅ DailyLog (12 JSON blobs + 11 child relationships)
│   │   ├── log_items.py                      ✅ 11 normalized child tables for daily_logs
│   │   └── generation.py                     ✅ GenerationOutput, AuditLog (immutable)
│   ├── repositories/
│   │   ├── __init__.py                       ✅ Re-exports all repository classes
│   │   ├── base.py                           ✅ BaseRepository[T] — generic CRUD
│   │   ├── company.py                        ✅ CompanyRepository, UserRepository
│   │   ├── project.py                        ✅ ProjectRepository, SiteRepository, ProjectWorkerRepository
│   │   ├── worker.py                         ✅ WorkerRepository (find_by_name for voice extraction)
│   │   ├── audio.py                          ✅ AudioRepository, SpeechTranscriptRepository
│   │   ├── daily_log.py                      ✅ DailyLogRepository (create_from_extraction_result)
│   │   └── generation.py                     ✅ GenerationRepository, AuditLogRepository
│   ├── seed/
│   │   ├── reference_data.py                 ✅ Idempotent seed: 25 trades, 22 stages, 16 cats, 16 PPE
│   │   └── sample_data.py                    ✅ Fixed-UUID demo company + project + daily log
│   └── migrations/
│       ├── env.py                            ✅ Alembic env — reads DATABASE_URL, imports all models
│       ├── script.py.mako                    ✅ Migration file template
│       └── versions/
│           └── 001_initial_schema.py         ✅ All 26 tables — PostgreSQL-native JSONB/UUID/TIMESTAMPTZ
│
├── alembic.ini                               ✅ SPRINT 6 — Alembic configuration
│
├── tests/ (Sprint 6 additions)               ✅ SPRINT 6 — NEW
│   ├── test_db_models.py                     ✅ 46 ORM model tests (SQLite in-memory)
│   ├── test_db_repositories.py              ✅ 50 repository CRUD + business logic tests
│   └── test_db_seed.py                       ✅ 27 seed count + idempotency + FK integrity tests
│
├── docs/DATABASE_ARCHITECTURE.md             ✅ SPRINT 6 — ER diagram + ADRs + migration guide
│
├── app/                                       ✅ SPRINT 7 — NEW — Production FastAPI backend
│   ├── main.py                               ✅ ASGI entry point (uvicorn app.main:app)
│   ├── create_app.py                         ✅ Application factory — middleware, routers, lifespan
│   ├── core/
│   │   ├── config.py                         ✅ Settings (pydantic-settings) — sole os.environ reader in app/
│   │   ├── security.py                       ✅ bcrypt password hashing + JWT encode/decode
│   │   └── dev_seed.py                       ✅ Dev-only demo login bootstrap
│   ├── api/
│   │   ├── dependencies.py                   ✅ get_db, get_current_user, require_role, get_app_settings
│   │   └── v1/
│   │       ├── health.py                     ✅ /health, /live, /ready, /version
│   │       ├── auth.py                       ✅ /auth/login
│   │       ├── audio.py                      ✅ /audio/upload, /audio/{id}/status
│   │       ├── daily_logs.py                 ✅ retrieval, review lifecycle, /generate, /outputs
│   │       └── projects.py                   ✅ /projects/{id}/daily-logs
│   ├── services/
│   │   └── pipeline_service.py               ✅ Background task: speech→extraction→DB→generation→DB
│   ├── schemas/                              ✅ Pydantic request/response models + APIResponse[T] envelope
│   └── middleware/                           ✅ request_id, logging, exception_handlers, cors
│
├── tests/test_api_*.py                        ✅ SPRINT 7 — NEW — 31 API tests (SQLite in-memory + TestClient)
│
├── docs/BACKEND_ARCHITECTURE.md               ✅ SPRINT 7 — Application flow, DI, ADRs, versioning
├── docs/BACKEND_STARTUP.md                    ✅ SPRINT 7 — Step-by-step run guide + troubleshooting
├── docs/CONTRIBUTING.md                       ✅ SPRINT 7 — Coding standards + "how to" guides
│
frontend/           ← Sprint 9+ (not yet created)
deployment/         ← Sprint 10+ (not yet created)
```

---

## Knowledge Base Status

| File | Status | What It Contains |
|------|--------|-----------------|
| `construction_stages.json` | ✅ FROZEN | 11 stages with workers, materials, hazards, duration, daily report fields |
| `construction_daily_log_schema.json` | ✅ FROZEN | Master JSON Schema v1.0.0 — 12 sections, 80+ fields |
| `construction_rules.json` | ✅ FROZEN | 38 rules: sequential, parallel, material/worker/weather/safety/quantity rules |
| `dependency_graph.json` | ✅ FROZEN | Full DAG with critical path, parallel groups, topological sort |
| `validation_rules.json` | ✅ FROZEN | 35 machine-readable validation rules for generators and AI validator |
| `construction_ontology.json` | ✅ FROZEN | Entity-relationship model: trades, materials, hazards, PPE, inspections |

---

## Schema Status

**ConstructionDailyLog v1.0.0** — FROZEN

| Section | Fields | Status |
|---------|--------|--------|
| Metadata | log_id, schema_version, log_date, log_source, review_status, audio_file_id, raw_transcript | ✅ |
| Project Context | project_id, site_address, client, foreman, dates, permit | ✅ |
| Construction Stage | current_stage (22 values), active_stages, completion percents | ✅ |
| Weather | conditions, temperatures, precipitation, impact level | ✅ |
| Workforce | totals, trades_on_site, late_arrivals, absences, visitors | ✅ |
| Work Completed | task descriptions, quantities, locations | ✅ |
| Materials | used_today, delivered, required_for_tomorrow, shortage_flags | ✅ |
| Equipment | usage tracking, condition, hours | ✅ |
| Safety | meeting, PPE, incidents (OSHA fields), hazards | ✅ |
| Delays | type enum, hours_lost, schedule_impact | ✅ |
| Tomorrow's Plan | tasks, materials to order, subcontractors, inspections | ✅ |
| Client Communication | contact method, concerns, change orders | ✅ |
| Attachments | photos, videos, GPS, AI analysis link | ✅ |
| Financials | daily costs by category (optional, future modules) | ✅ |
| AI Generated Outputs | 4 AI service output sections (populated by Sprint 5) | ✅ |
| Audit | created_by, reviewed_by, version tracking | ✅ |

---

## AI Models Planned

| Model | Provider | Purpose | Sprint | Cost |
|-------|----------|---------|--------|------|
| Faster Whisper (base) | Open source, local (CTranslate2) | Speech-to-text | Sprint 3 — ✅ Done | Free |
| openai/gpt-oss-120b | Groq cloud API (free tier) | Information extraction | Sprint 4 — ✅ Framework done | Free (cloud) |
| openai/gpt-oss-120b | Groq cloud API (free tier) | Report/email generation | Sprint 5 — ✅ Done | Free (cloud) |

Speech-to-text runs fully locally (Faster Whisper). Language model inference uses Groq's free-tier cloud API — no per-token charges at current usage. `GROQ_API_KEY` must be set in `.env`.

---

## Database Status

**Sprint 6 COMPLETE.** Production-grade persistence layer built and tested.

| Metric | Value |
|---|---|
| Tables | 26 |
| ORM Models | 26 (SQLAlchemy 2.x Mapped[T] style) |
| Repositories | 9 classes, ~35 methods |
| Migrations | 1 (001_initial_schema — all 26 tables) |
| Seed scripts | 2 (reference_data: 79 rows; sample_data: demo company + log) |
| New tests | 123 (all passing) |
| Full suite | 718 passed, 1 skipped |

**Tables created:**
4 reference + companies + users + workers + projects + sites + project_workers + audio_files + speech_transcripts + daily_logs + 11 log child tables (trades, work items, materials ×3, equipment, incidents, hazards, delays, inspections) + generation_outputs + audit_logs

See `docs/DATABASE_ARCHITECTURE.md` for full ER diagram, ADRs, and migration guide.

---

## Datasets Status

| Dataset | Sprint | Status | Location |
|---------|--------|--------|----------|
| Construction stages knowledge | 1 | ✅ Done | `knowledge/construction_stages.json` |
| ConstructionDailyLog schema | 1 | ✅ Done | `knowledge/construction_daily_log_schema.json` |
| Construction rules | 1.1 | ✅ Done | `knowledge/construction_rules.json` |
| Validation rules | 1.1 | ✅ Done | `knowledge/validation_rules.json` |
| Daily site logs | 2 | ✅ Done (generator) | `datasets/daily_logs/` |
| Safety toolbox talks | 2 | ✅ Done (generator) | `datasets/safety_talks/` |
| Material database | 2 | ✅ Done (generator) | `datasets/materials/` |
| Customer progress examples | 2 | ✅ Done (generator) | `datasets/customer_updates/` |
| Project schedules | 2 | ✅ Done (generator) | `datasets/schedules/` |
| Sample audio (10 synthetic WAVs) | 3 | ✅ Done | `data/sample_audio/` |

Generators are complete and tested; large-scale dataset runs (the actual 5,000/1,000/500-record files) are produced on demand via `python generate.py` and are not committed to git (see `datasets/README.md`).

---

## Key Technical Decisions (Summary)

| # | Decision | Choice | Reason |
|---|----------|--------|--------|
| ADR-001 | Schema format | JSON Schema draft-07 | Language-agnostic, generates Pydantic+TypeScript |
| ADR-002 | Primary keys | UUID v4 | Security, offline generation, no collisions |
| ADR-003 | Null handling | Explicit `["type","null"]` | Distinguish AI-null from schema-missing |
| ADR-004 | Schema organization | 12 sections | Maps to DB tables, AI prompt sections |
| ADR-005 | AI runtime | No paid APIs (Groq free-tier cloud) | No per-token cost, open source; see ADR-015 |
| ADR-006 | Knowledge format | JSON files | Version control, AI-friendly, no DB required |
| ADR-007 | Training data | Synthetic generation | No public dataset exists |
| ADR-008 | Stage granularity | 22 enum values | More granular than 11 phases |
| ADR-009 | Generation architecture | Production framework over scripts | Reusable, testable, scales to 500k+ |
| ADR-010 | Record generation method | Project simulation, not random | Guarantees sequencing/business-rule correctness |
| ADR-011 | Generator memory model | Streaming generators | Same peak memory at 500k as at 5k |
| ADR-012 | Speech engine boundary | `BaseSTTEngine` abstraction | Faster Whisper swappable without touching callers |
| ADR-013 | Whisper model loading | Lazy (on first `transcribe()`) | Importing `speech` never downloads/loads a model |
| ADR-014 | STT result shape | Structured `SpeechProcessingResult` | Never plain text; failures are data, not exceptions |
| ADR-015 | Extraction engine boundary | `BaseLLMProvider` + `EngineFactory` | Groq (or any provider) swappable without touching callers; MockExtractionEngine for tests |
| ADR-016 | Extraction result shape | Structured `ExtractionResult` | Reuses Sprint 2 validation; field confidences; never raw dict |
| ADR-017 | Generation prompts | Versioned `.md` files | Product artifacts; non-developers iterate without Python |
| ADR-018 | Generation output models | Pydantic `BaseModel` | Sprint 7 FastAPI readiness; `model_dump()` for free |
| ADR-019 | Shared engine | One engine, instructions in user message | Respects Sprint 4 FROZEN interface |
| ADR-020 | Prompt location | `generation/prompts/` not `app/prompts/` | `app/` is Sprint 7; consistent with `extraction/prompts/` |
| ADR-021 | Prompt cache invalidation | Mtime-aware per-load check | No restart needed when prompts are edited |
| ADR-022 | Prompt registry | `PromptRegistry` + `DEFAULT_PROMPT_REGISTRY` | Domain-level discovery; separates I/O from domain |
| ADR-023 | Service registry | `ServiceRegistry` + `DEFAULT_SERVICE_REGISTRY` | Open/Closed extensibility; 1 class + 1 register = new service |
| ADR-024 | Generation ID | UUID4 per generate() call in `ServiceMetadata` | Cross-log/DB correlation key |
| ADR-025 | Observability | In-process events + metrics (no cloud) | Forward-compatible; sprint 7 wires persistence |

---

## Known Issues and Limitations

| Issue | Severity | Resolution Plan |
|-------|----------|----------------|
| Schema is English-only | Medium | Future sprint: multi-language field support |
| USA-centric standards (OSHA, IRC) | Low | Future: international standards module |
| Python validation tooling | Resolved | Built in Sprint 4 — `SchemaValidator` in `extraction/validators/schema_validator.py` |
| Weather auto-fetch not designed | Low | Future: OpenWeatherMap API integration |
| 11-stage research vs 22-stage schema gap | Resolved | Ontology + dependency graph cover all 22 stages |

---

## Sprint Completion Checklist

### Sprint 1 Final Checklist ✅
- [x] All 11 construction stages documented with full detail
- [x] ConstructionDailyLog JSON Schema v1.0.0 complete
- [x] Construction rules (38 rules) created and validated
- [x] Dependency graph (23 nodes, 33 edges) created
- [x] Validation rules (35 rules) created, machine-readable
- [x] Construction ontology created with entity-relationship model
- [x] All documentation updated (CHANGELOG, DECISIONS, ROADMAP, NEXT_SPRINT, HANDOVER)
- [x] PROJECT_STATE.md updated
- [x] No placeholder files, no dummy implementations
- [x] No backend code (Sprint 2+)
- [x] No database (Sprint 6+)

**Sprint 1 Status: COMPLETE — FROZEN**

### Sprint 2 Final Checklist ✅
- [x] Production-grade `dataset_generation_framework/` (config, core, generators, validation, exporters, statistics)
- [x] All 5 generators implemented (daily logs, schedules, safety talks, materials, customer updates)
- [x] Streaming architecture — same peak memory at any scale
- [x] 4-phase ValidationPipeline (blocking → errors → warnings → info)
- [x] JSONL and CSV exporters with batching
- [x] `generate.py` CLI entry point
- [x] Full test suite (`test_knowledge_loader.py`, `test_stage_machine.py`, `test_validation_pipeline.py`, `test_generators.py`, `test_integration.py`)
- [x] Documentation updated (CHANGELOG, DECISIONS, PROJECT_STATE)
- [x] No backend code, no database

**Sprint 2 Status: COMPLETE — APPROVED & FROZEN**

### Sprint 3 Final Checklist ✅
- [x] Standalone, engine-agnostic `speech/` framework — zero imports from `dataset_generation_framework/` or `knowledge/`
- [x] `BaseSTTEngine` abstraction — `faster_whisper` imported in exactly one file (`speech/whisper/engine.py`)
- [x] Lazy Whisper model loading (loads on first `transcribe()`, not at import/construction)
- [x] 8 blocking + 3 non-blocking audio validation checks, run before any transcription
- [x] Structured `SpeechProcessingResult` — never plain text, never raises for expected failures
- [x] Optional preprocessing (normalization, noise reduction) with graceful no-op fallback
- [x] Postprocessing: hallucination removal, filler stripping, construction-term normalization
- [x] Multiple export formats: JSON, JSONL, text, verbose text
- [x] `transcribe.py` CLI (single file, batch, dry-run, format/model overrides)
- [x] Dynamic configuration via `SpeechProcessingConfig.from_env()`
- [x] Full test suite — 144 passed, 1 skipped (real-Whisper test correctly gated by `faster_whisper` availability)
- [x] Full repo regression suite — 256 passed, 1 skipped, no regressions
- [x] 10 synthetic sample audio files + README for future WER testing
- [x] `docs/AI_PIPELINE.md` and `docs/SPEECH_PIPELINE.md` written
- [x] Documentation updated (CHANGELOG, DECISIONS — ADR-012/013/014, PROJECT_STATE)
- [x] No paid APIs, no cloud inference — 100% local, open source
- [x] No AI field extraction, no database writes, no streaming transcription (explicitly out of scope, deferred to Sprint 4+)

**Sprint 3 Status: COMPLETE — APPROVED & FROZEN**

### Sprint 4 Final Checklist ✅
- [x] Standalone, engine-agnostic `extraction/` framework — zero direct imports of Groq in business logic
- [x] `BaseLLMProvider` abstraction — Groq API calls confined to `extraction/engines/groq_engine.py`
- [x] `ExtractionPipeline.extract(transcript_text) -> ExtractionResult` — never raises for expected failures
- [x] `ExtractionResult` — structured, fully serializable, with per-field confidence scores
- [x] Prompt engineering: `PromptBuilder` with schema-derived enum context, editable `system_prompt.txt`
- [x] JSON repair: 3-strategy `repair_json()` handles markdown fences and prose-wrapped JSON
- [x] Two-stage validation: JSON Schema structural check + Sprint 2 `ValidationPipeline` business rules (`applies_to="ai_extraction"`)
- [x] Retry with exponential backoff for LLM call failures
- [x] Graceful degradation: `is_available()` check before extraction; clear install instructions in error message
- [x] `extract.py` CLI (from file, from text, --check, --provider, --model, --output, --log-date overrides)
- [x] Full test suite — 66 Sprint 4 tests passed, 1 skipped (real-Groq test gated by GROQ_API_KEY), 322 total passed across full repo
- [x] No paid APIs. Groq free-tier cloud API (zero cost at current usage). No GPU required.
- [x] No AI generation services (Sprint 5), no database (Sprint 6)

**Sprint 4 Status: COMPLETE — PENDING APPROVAL**

---

## Sprint 6 Final Checklist ✅
- [x] SQLAlchemy 2.x ORM models — all 26 tables, Mapped[T] style
- [x] 4 composable mixins (UUID PK, Timestamp, SoftDelete, AuditUser)
- [x] Repository pattern — BaseRepository[T] + 8 typed repositories
- [x] Alembic migration — `001_initial_schema.py` with PostgreSQL-native JSONB/UUID/TIMESTAMPTZ
- [x] Idempotent reference data seed (25 trades, 22 stages, 16 material cats, 16 PPE types)
- [x] Fixed-UUID sample data seed (1 company, 1 user, 3 workers, 1 project, 1 approved log)
- [x] 123 new tests — all passing (SQLite in-memory, no PostgreSQL required)
- [x] Full test suite — 718 passed, 1 skipped, 0 regressions
- [x] `docs/DATABASE_ARCHITECTURE.md` — ER diagram, ADR-026/027/028/029/030, migration guide
- [x] All project documentation updated
- [x] No placeholder code, no TODO stubs, no incomplete implementations

**Sprint 6 Status: APPROVED & FROZEN**

---

## Sprint 7 Final Checklist ✅

- [x] Application factory pattern (`app/create_app.py`) with lifespan-based production safety checks (refuses to start with the default JWT secret or wide-open CORS in production)
- [x] `app/core/config.py` — `Settings` (pydantic-settings), the sole `os.environ` reader in `app/`; delegates to existing `DatabaseConfig`/`ExtractionConfig`/`GenerationConfig`/`SpeechProcessingConfig.from_env()` rather than duplicating env vars
- [x] `app/core/security.py` — bcrypt password hashing (passlib) + JWT encode/decode (python-jose)
- [x] Dev-only demo login (`admin@example.com`), seeded via `app/core/dev_seed.py` without `database/` depending on `app/` (see `docs/BACKEND_ARCHITECTURE.md` §8)
- [x] Standard response envelope — `{success, message, data, metadata, errors, timestamp, request_id}` on every response, success or error
- [x] `/api/v1/` versioning — structured so `/api/v2` can be added without touching `v1/`
- [x] 4 health endpoints with distinct semantics: `/health` (full diagnostic), `/live`, `/ready`, `/version`
- [x] JWT auth: `POST /auth/login`, `Depends(get_current_user)`, `Depends(require_role(...))`
- [x] Audio upload + background-task pipeline orchestration (speech → extraction → DB → generation → DB), Celery-ready extension point documented
- [x] Daily-log review lifecycle (`/submit`, `/approve`, `/reject`) delegating entirely to the frozen `DailyLogRepository` state machine — `ValueError` → HTTP 409 via centralized exception handling
- [x] `/daily-logs/{id}/generate` and `/daily-logs/{id}/outputs`
- [x] `/projects/{id}/daily-logs` with pagination metadata
- [x] Centralized exception handling — 5 handlers, every error shape-consistent with success responses
- [x] Structured request logging — request_id, method, path, status, duration_ms; never logs bodies/headers/secrets
- [x] Async DB session (`get_async_session()`) added to `database/session.py`, additive only — repository layer intentionally stays sync (see `docs/BACKEND_ARCHITECTURE.md` §7 for the full rationale and future migration path)
- [x] 31 new API tests, SQLite in-memory + `TestClient`, zero live-DB dependency for CI
- [x] Two real bugs caught and fixed during manual verification: `Depends(get_settings)` bypassing `create_app(settings=...)` overrides (fixed via `get_app_settings()`), and `.env` not loading under a real `uvicorn` launch (fixed via `load_dotenv()` in `app/main.py`)
- [x] Full suite: **801 passed, 1 skipped, 0 regressions** (post-Sprint-7 hardening — see `docs/BACKEND_ARCHITECTURE.md` §11 for the five bugs found and fixed after initial Sprint 7 completion)
- [x] Live-verified over real HTTP against real PostgreSQL and real Groq — not just `TestClient`
- [x] `docs/BACKEND_ARCHITECTURE.md`, `docs/BACKEND_STARTUP.md`, `docs/CONTRIBUTING.md` — all new
- [x] No placeholder code, no TODO stubs, no incomplete implementations
- [x] No Sprint 1–6 code modified except the one additive, documented exception (`database/session.py`)

**Sprint 7 Status: APPROVED & FROZEN**

---

## Sprint 8 Final Checklist ✅

- [x] **Subsystem 1 (Authentication Core):** `UserSession` + `PasswordResetToken` tables, `AuthService` (login/refresh/logout/logout-all/change-password/forgot-password/reset-password), 7 new endpoints, opaque server-backed refresh tokens with rotation (ADR-035)
- [x] **Subsystem 2 (RBAC & Permissions):** `Permission` enum + `ROLE_PERMISSIONS`, `require_permission()` replacing hardcoded role lists, all 9 daily-log/audio/project endpoints now permission-gated (7 previously had none), `system_admin` role added without modifying the 6 existing frozen roles (ADR-036)
- [x] **Subsystem 3 (Multi-Tenancy):** `TenantScopedRepository` + `TenantContext`, repository-layer scoping (not router-layer), `system_admin` cross-tenant bypass via explicit audited methods, 404 for cross-tenant access (ADR-037, ADR-038)
- [x] **Subsystem 4 (User Management):** `UserService`, 8 new endpoints (create/list/get/update-profile/deactivate/restore/assign-role/unlock), role-assignment hierarchy with last-admin protection
- [x] **Subsystem 5 (Security Hardening):** `RateLimiter` Protocol + `MemoryRateLimiter` (ADR-041), account lockout (5 attempts/15 min, configurable), rate limiting on login + forgot-password, security response headers, admin unlock
- [x] **Subsystem 6 (Audit Logging):** `AuditLog` extended with 5 structured columns (ADR-039), `safe_log_event()` fail-open wrapper with one deliberate exception (ADR-040), 20+ event types across authentication/lockout/user-management/security
- [x] `docs/AUTHENTICATION_ARCHITECTURE.md`, `docs/AUTHORIZATION_ARCHITECTURE.md` — new
- [x] 121 new tests across 7 new test files; full suite **913 passed, 1 skipped, 0 regressions**
- [x] Live-verified over real HTTP against real PostgreSQL for every subsystem
- [x] Three real bugs found and fixed during manual verification (account-lockout persistence, audit-event persistence, `UserRead` schema UUID typing) — see `docs/DECISIONS.md` "Known Bugs Found and Fixed — Sprint 8"
- [x] No Sprint 1–7 code modified except additive extensions (new columns, new tables) and the documented bug fixes
- [x] No placeholder code, no TODO stubs, no incomplete implementations

**Sprint 8 Status: APPROVED & FROZEN** (approved 2026-08-19)

---

## Post-Sprint-8 Work (2026-08-19, before Sprint 9 approval)

Not part of the frozen Sprint 8 scope above — done afterward, ahead of Sprint 9, as fixes and one new capability:

- **Groq model migration (critical fix):** `llama-3.3-70b-versatile` was decommissioned by Groq — every real LLM call (extraction, all 4 generation services) was 404ing in production despite `/api/v1/health` reporting the engine "up". Root cause: `GroqEngine.is_available()` only checked that the API key was valid, not that the *configured model* was reachable. Migrated the default model to `openai/gpt-oss-120b` everywhere (`extraction/config.py`, `generation/config.py`, `.env`, `.env.example`), and `is_available()` now checks the configured model against Groq's live model list. See `docs/DECISIONS.md`'s "Known Bugs Found and Fixed — Post-Sprint-8" section (this was a bug fix, not an ADR — ADR-042 below is the unrelated grounded-Q&A decision).
- **Live-Groq test was permanently skipped:** `tests/test_extraction_pipeline.py`'s only real-API test gates on `GROQ_API_KEY` being set, but pytest never called `load_dotenv()` — only `app/main.py` did — so the env var was always empty under pytest and the test silently skipped on every run, including in the "913 passed, 1 skipped" baseline reported at Sprint 8 completion. `tests/conftest.py` now loads `.env` for the whole suite; the test now runs and passes. This is why the skip count changed from 1 to 0.
- **Grounded project Q&A (new, ADR-042):** `POST /api/v1/projects/{id}/ask` — answers a free-form question using only a project's recent approved daily logs as context, refusing rather than guessing when the logs don't cover it. New `ProjectQAService`, `generation/prompts/project_qa.md`, `DailyLogRepository.list_recent_with_children_scoped()`. See `docs/AI_SERVICES.md` §12 for the full request pipeline.
- **Rate limiting on Groq-calling endpoints (security fix):** `POST /daily-logs/{id}/generate` and the new `/ask` endpoint had no rate limit — any authenticated user could exhaust the company's shared Groq free-tier quota alone. Added `Settings.rate_limit_ai_generation_attempts` (default 20/60s per user) via `app/core/rate_limit.py`'s new `enforce_ai_generation_rate_limit()`, reusing Sprint 8's `RateLimiter` Protocol.
- **Test suite:** 930 passed, 0 skipped (up from 913 passed, 1 skipped) — 16 new tests for the Q&A feature, 2 new rate-limit tests, plus the previously-skipped live-Groq test now actually running.
- **Doc drift correction:** `BACKEND_STARTUP.md`, `CONTRIBUTING.md`, `DATABASE_ARCHITECTURE.md` and this file had several stale claims left over from Sprint 6/7 (migration head `001` instead of `004`, 26 tables instead of 28, test counts as low as 718/777) — corrected across all of them.

---

## Sprint 9 Final Checklist ✅

Scoped as one combined sprint (task queue + email + frontend), per the decision point `docs/NEXT_SPRINT.md` itself flagged rather than splitting into Sprint 9/10.

- [x] **Celery + Redis task queue:** `celery_app.py` (Redis broker db 0, result backend db 1), `app/tasks/pipeline_tasks.py` wraps `run_pipeline()` unchanged with Celery-level `autoretry_for` for the outer failure modes its own internal per-stage handling doesn't cover (unguarded DB writes, real worker crashes). `app/api/v1/audio.py`'s call site: `background_tasks.add_task(run_pipeline, id)` → `run_pipeline_task.delay(str(id))`. Redis run via Docker (`redis:7-alpine`), not a native install. Verified live: a real worker processed a real enqueued task end-to-end.
- [x] **Real email delivery:** `app/services/email_sender.py` — `EmailSender` Protocol, `DevConsoleEmailSender` (zero-setup dev/CI default) and `SMTPEmailSender` (real delivery, any provider). `AuthService.forgot_password()` now emails a reset link instead of returning the raw token; that Sprint 8 behavior is now explicit opt-in via `Settings.expose_raw_reset_token_in_response` (default off). Found and fixed while verifying this live: `app/main.py` never called `logging.basicConfig()`, so every `logger.info()` in `app/` — not just this feature's — was silently dropped.
- [x] **RedisRateLimiter (ADR-041 migration):** `app/core/rate_limit.py` — Redis sorted set + Lua script for cross-process atomicity, replacing the Sprint 8 documented limitation (per-process counters, reset on restart). `get_rate_limiter()` is now a proper FastAPI dependency (`Depends(get_app_settings)`) rather than a zero-arg getter. Verified live: a real login attempt wrote a real sorted-set entry into the real Redis container.
- [x] **React frontend core:** Vite + React + TypeScript under `frontend/`. Login/logout, password reset flow, dashboard (daily-log list + grounded Q&A via `POST /projects/{id}/ask`), voice recording (`MediaRecorder` → upload → poll `GET /audio/{id}/status`), daily-log review (approve/reject, RBAC-aware). Verified with a real Playwright-driven browser session against the real running backend — every screen exercised, zero console errors, zero failed API requests, including a real approve-transition DB write.
- [x] 15 new frontend component tests (Vitest + Testing Library) + 26 new backend tests (Celery eager-mode, email delivery, RedisRateLimiter against real Redis with a concurrency-atomicity test) — full backend suite: **957 passed, 0 skipped, 0 regressions**.
- [x] `docs/BACKEND_STARTUP.md` extended with Redis/Celery/frontend startup steps; `frontend/README.md` added.
- [x] No Sprint 1–8 code modified except additive extensions and the documented `app/main.py` logging fix.
- [x] No placeholder code, no TODO stubs, no incomplete implementations.

**Known, documented gap carried into Sprint 10:** no `GET /projects` list endpoint exists yet (full project CRUD was already deferred before Sprint 9) — the frontend Dashboard takes a project ID typed in directly rather than a picker. See `frontend/README.md`.

**Sprint 9 Status: APPROVED & FROZEN** (approved 2026-08-19)

---

## Sprint 10 Final Checklist ✅

All 7 deliverables from `docs/NEXT_SPRINT.md` (Sprint 10 spec) completed, each tested and verified live against the real backend/database in a real browser — not just against the mock-based test suite.

- [x] **`GET /projects` + Dashboard picker (Deliverable 1):** closes the gap Sprint 9 carried forward. `ProjectRepository.list_by_company()` already existed; the router derives `company_id` from `TenantContext` itself since that method takes a raw id, not a `TenantContext`. Verified live: the real seeded project's name renders in the picker, auto-selects, falls back to the first project if a stale localStorage id no longer exists.
- [x] **View + regenerate generated documents (Deliverable 2):** `DocumentsPanel.tsx` surfaces the 4 documents `POST /daily-logs/{id}/generate` already produced (Sprint 5/7). **Bug found and fixed:** regenerating accumulated every historical copy instead of showing the current 4 — `GenerationRepository.list_latest_for_log()` (a `ROW_NUMBER()` window query) fixes it. See ADR / Known Bugs in `docs/DECISIONS.md`.
- [x] **Mark documents as sent (Deliverable 3):** `POST /daily-logs/{id}/outputs/{output_id}/mark-sent`, new `Permission.DAILY_LOG_SEND_OUTPUT`. Tracks only — no real email delivery to a client (no client contact field exists yet, explicitly out of scope).
- [x] **Safety-talk PDF export (Deliverable 4):** genuinely new capability — `app/services/pdf_export.py`, `reportlab` chosen over `weasyprint` for Windows install reliability (ADR-046). **Bug found and fixed:** real Groq output rendered black-box glyphs (■) for Unicode punctuation outside reportlab's default font's coverage — `_sanitize_for_pdf_font()` fixes it.
- [x] **Material-reminder priority UI (Deliverable 5):** `MaterialReminderContent.tsx`, a small parser for the fixed CRITICAL/HIGH/MEDIUM/LOW heading shape `generation/prompts/material_reminder.md` always produces, rendered as color-coded badges.
- [x] **Basic analytics (Deliverable 6):** `GET /projects/{id}/analytics` — completion trend + delay frequency, computed from approved logs only (same trust boundary as ADR-042's grounded Q&A). `recharts` chosen for its composable React API.
- [x] **Client-portal RBAC (Deliverable 7):** no new role/permission model needed (Sprint 8's `client` role already scoped correctly) — but verification found a real gap: Generate, Mark-as-sent, and the Record page were shown to every role unconditionally, including roles that would 403 on click. `frontend/src/auth/roles.ts` fixes it. Verified live with a real `client`-role login.
- [x] 65 new backend tests + 51 new frontend tests (up from Sprint 9's 957 backend / 15 frontend). Full suite: **997 backend passed, 66 frontend passed, 0 skipped, 0 regressions.**
- [x] 3 real bugs found and fixed during live verification, all documented in `docs/DECISIONS.md`'s Sprint 10 "Known Bugs" section (duplicate documents, PDF font corruption, missing frontend RBAC gating) — none caught by the mock-based test suite; all three found only because each deliverable was exercised in a real browser against the real backend, not just tested in isolation.
- [x] No Sprint 1–9 code modified except additive extensions (new endpoints, new permission, new repository methods) and the documented bug fixes.
- [x] No placeholder code, no TODO stubs, no incomplete implementations.

**Sprint 10 Status: APPROVED & FROZEN** (approved 2026-09-15)

Note on this approval's timing: the checklist above was completed and this section written on 2026-08-19, but the status line itself was never actually updated to APPROVED at the time — a commit titled "docs: approve Sprint 10" (`6a172d0`) asserted the approval in its message without its diff making the change. This was caught during the 2026-09-15 resume audit (`docs/RESUME_AUDIT_2026-09-15.md`), which independently re-verified all 7 deliverables live (a fresh end-to-end pipeline run plus a full 11-step Playwright browser session, both passing) before formally applying the approval here.

---

## Sprint 11 Final Checklist ✅

All 7 deliverables from `docs/NEXT_SPRINT.md` (Sprint 11 spec) completed, each tested and verified live against the real backend/database — and, for the frontend, a real browser — not just against the mock-based test suite.

- [x] **`ProjectSchedule`/`ScheduleTask` tables (Deliverable 1):** `database/models/schedule.py`, migration `005_scheduling.py`. One schedule per project (`UniqueConstraint`), no revision history — ADR-047. Verified live: `alembic upgrade head` applied cleanly against the real PostgreSQL database; `alembic check` shows no schedule-specific drift.
- [x] **Gantt chart generation (Deliverable 2):** `GET /projects/{id}/schedule`, `database/repositories/schedule.py`'s `build_schedule_for_project()`. Frontend: `frontend/src/components/SchedulePanel.tsx`, a hand-rolled SVG Gantt (no third-party library) — decision documented alongside ADR-047/048/049. Verified live in a real Playwright browser session: 23 task rows, correct critical-path coloring, zero overlaps, zero console errors.
- [x] **Schedule variance detection (Deliverable 3):** `app/services/schedule_service.py`'s `compute_variance()` — pure date arithmetic, no AI call (ADR-048). Computed at read time in `GET /projects/{id}/schedule`'s response, never persisted.
- [x] **Populating actual dates from daily logs (Deliverable 4):** `POST /daily-logs/{id}/approve` now calls `ScheduleRepository.record_actual_progress()`, synchronous (design decision: this is a handful of row reads/writes, not worth Celery's async overhead). Deliberately best-effort and transactionally isolated from the approval itself — see the Known Bugs section below for a real ordering bug caught before this shipped. Verified live: approving a real log set `schedule_tasks.actual_start_date` correctly.
- [x] **Critical path tracking (Deliverable 5):** `compute_critical_path()`, a real CPM forward/backward pass including inter-task lag, computed once at schedule-creation time. Deliberately diverges from `dependency_graph.json`'s own generic "typical" critical path when a project's real computation finds a genuinely longer branch — documented as correct-by-design in ADR-049, not a bug.
- [x] **Delay impact prediction (Deliverable 6):** `propagate_delay_impact()`, a breadth-first graph walk — graph arithmetic, not ML (ADR-048). `database/repositories/daily_log.py`'s `get_critical_path_delays_scoped()` feeds it from real `LogDelay` rows with `schedule_impact='critical_path_impacted'`. Verified live: a real critical-path-impacting delay correctly pushed `delay_adjusted_completion_date` out by exactly the recorded `days_lost_to_schedule`.
- [x] **Tests (Deliverable 7):** `tests/test_critical_path.py` (20 tests — linear chains, diamonds, lag, cycle detection, variance, delay propagation, plus one integration check against the real 23-node knowledge file), `tests/test_api_schedule.py` (19 tests — creation, idempotency, tenant isolation, the approval hook, delay-impact propagation), `frontend/src/components/SchedulePanel.test.tsx` (9 tests). Full suite: **1036 backend passed, 82 frontend passed, 0 skipped, 0 regressions.**
- [x] 4 real bugs found and fixed during implementation/live verification (see Known Bugs below) — none caught by a mock-based test in isolation; all four found only because each deliverable was exercised against the real running backend/database, not just tested with fixtures.
- [x] No Sprint 1–10 code modified except additive extensions (new endpoints, new repository methods, the approval-hook addition) — no rewrites.
- [x] No placeholder code, no TODO stubs, no incomplete implementations.

**Sprint 11 Status: APPROVED & FROZEN** (approved 2026-09-16)

Between Sprint 11's completion (2026-09-15) and this approval, a post-resume-audit cleanup pass fixed the P1/P2 backlog `docs/RESUME_AUDIT_2026-09-15.md` had identified (lossy manual-regenerate reconstruction, `processing_status="complete"` masking a failed generation stage, permanent `alembic check` drift on 22 JSON columns plus two narrower schema mismatches, and several stale doc citations) — see `docs/DECISIONS.md`'s "Known Bugs Found and Fixed — Post-Resume-Audit Cleanup" and `docs/CHANGELOG.md`. Full suite verified at 1042 backend + 86 frontend passing, both P1 fixes confirmed live against the real database, before Sprint 11 was marked approved.

---

## Sprint 12 Final Checklist ✅

All 7 deliverables from `docs/NEXT_SPRINT.md` (Sprint 12 spec) completed, each tested and verified live against the real backend/database — and, for the frontend, a real browser — not just against the mock-based test suite.

- [x] **`InventoryItem`/`PurchaseOrder` tables (Deliverable 1):** `database/models/inventory.py`, migration `006_inventory.py`. Project-scoped (not global), plain-string supplier fields, no FK from `LogMaterialDelivered.purchase_order_number` (soft link, same reasoning as Sprint 11's `linked_schedule_task_id` decision) — see ADR-050. Verified live: `alembic upgrade head` applied cleanly against the real PostgreSQL database.
- [x] **Material consumption tracking (Deliverable 2):** `InventoryRepository.record_material_consumption_from_log()`, wired into `POST /daily-logs/{id}/approve` alongside Sprint 11's schedule hook — same transaction-isolation discipline (approval commits first, reconciliation attempted independently after). Verified live: approving a real log with real `materials_used`/`materials_delivered` data correctly created and updated `InventoryItem` rows in the real database.
- [x] **Auto-generated purchase orders (Deliverable 3):** `InventoryRepository.check_and_create_reorder_purchase_orders()` — a flat `reorder_point × 2` restock quantity (ADR-051), always `status="draft"`, deduplicated against any already-open auto-generated PO. `GET /projects/{id}/inventory`, `POST/PATCH .../purchase-orders`. Verified live: a real log consuming material below its configured reorder point produced exactly one draft PO for the correct quantity; a second consuming log did not duplicate it.
- [x] **Lead-time warnings (Deliverable 4):** `app/services/inventory_service.py`'s `compute_lead_time_warning()` — pure date arithmetic, no AI call, cross-referencing `InventoryItem.applicable_stage_id` against Sprint 11's real `ScheduleTask` rows. Computed at read time in `GET /projects/{id}/inventory`'s response, never persisted (same pattern as Sprint 11's variance/delay-impact fields). Verified live: a configured item produced the correct overdue warning against the real schedule, and submitting its purchase order correctly suppressed it.
- [x] **Frontend inventory panel (Deliverable 5):** `frontend/src/components/InventoryPanel.tsx` — expandable item rows, reorder-point status badges (reusing `MaterialReminderContent.tsx`'s existing badge color language), a create-purchase-order form, and inline status updates. Verified live in a real Playwright browser session: empty state, populated state after a real approval, PO creation, and PO status update all rendered correctly with zero console errors.
- [x] **Supplier integration preparation (Deliverable 6):** explicitly scoped to preparation only — `preferred_supplier`/`supplier` stay plain strings, no real supplier API integration, no normalized `suppliers` table built speculatively. See ADR-050.
- [x] **Tests (Deliverable 7):** `tests/test_lead_time_warnings.py` (9 tests — pure-function, hand-built fixtures, matching Sprint 11's `test_critical_path.py` approach), `tests/test_api_inventory.py` (16 tests — reconciliation math, tenant isolation, auto-PO deduplication, lead-time cross-referencing), `frontend/src/components/InventoryPanel.test.tsx` (11 tests). Full suite: **1067 backend passed, 97 frontend passed, 0 skipped, 0 regressions.**
- [x] No Sprint 1–11 code modified except additive extensions (new endpoints, new repository methods, the approval-hook addition) — no rewrites.
- [x] No placeholder code, no TODO stubs, no incomplete implementations.

**Sprint 12 Status: APPROVED & FROZEN** (approved 2026-09-16)

## Sprint 13 Final Checklist ✅

All 7 deliverables from `docs/NEXT_SPRINT.md` (Sprint 13 spec) completed. No new database tables — every deliverable is a read-only aggregation over data Sprints 6–12 already persist, extending `GET /projects/{id}/analytics` (Sprint 10) with new fields rather than proliferating endpoints. Each deliverable tested and verified live against the real backend/database and, for the frontend, a real browser — not just the mock-based test suite.

- [x] **Completion-trend enrichment (Deliverable 1):** `projected_completion_date`/`delay_adjusted_completion_date`, sourced from Sprint 11's `ProjectSchedule` when one exists — `null` otherwise. Shown as a text summary above the "Completion trend" chart rather than a graphical reference line, since that chart's x-axis is categorical (actual log dates), not a continuous time scale — a `ReferenceLine` there would silently misplace or fail to render (ADR-052). `_compute_delay_adjusted_completion()` extracted so the schedule and analytics endpoints share one computation instead of two independently-drifting copies. Verified live: a real schedule's dates matched exactly between both endpoints; browser-verified with a real screenshot.
- [x] **Delay pattern analysis by trade (Deliverable 2):** `delay_frequency_by_trade` — `DailyLogRepository.get_delay_frequency_by_trade_scoped()` joins `LogTradeOnSite` to `LogDelay` on a shared `daily_log_id` (broad "on site that day" join, not text-matching `tasks_affected` against work items — ADR-053). Verified live against real seeded pipeline data: six trades each correctly credited with the one delay recorded that day.
- [x] **Safety incident trends (Deliverable 3):** `safety_incident_trend` (per log_date) and `safety_incident_breakdown` (per incident_type), both reporting `incident_count` alongside `osha_recordable_count` — an unassessed (`NULL`) `osha_recordable` flag counts toward the former but never the latter, since "not yet assessed" isn't "assessed as not recordable" (ADR-054). Unlike every other section, "Safety incidents" never hides when empty — it states "No safety incidents recorded" explicitly. Verified live: inserted and cleaned up a real incident against the running database, confirmed correct aggregation both ways.
- [x] **Productivity by stage and trade (Deliverable 4):** `productivity_by_stage_trade` — average `LogWorkItem.task_completion_percent` grouped by `(current_stage, trade)`, excluding work items with no recorded percent, `work_item_count` returned alongside every average so a single-item average can't be mistaken for a trend (ADR-055). Deliberately labeled "Average reported completion by stage / trade" in the UI, not bare "productivity" — not man-hours-per-unit, not cost-adjusted, not comparable to a planned rate. Verified live against the seeded project's real work items: three `framing_carpenter` items on `framing` averaging exactly 78.33%.
- [x] **Client-facing progress portal (Deliverable 5):** Frontend-only curation, not a new backend authorization path — `GET /projects/{id}/analytics` returns the identical response to every role. `client`-role users don't see "Delay frequency by trade" or "Safety incidents" (staff-internal risk/planning signal); everything else stays visible (ADR-056), following Sprint 10 Deliverable 7's "same app, fewer buttons" precedent exactly. Live-verified with a real `client`-role user logged into a real browser, contrasted against the same project as `admin` — the same method that caught Sprint 10's analogous client-role bug.
- [x] **Company-wide view scope decision (Deliverable 6):** Explicitly decided against — no cross-project dashboard this sprint. None of Deliverables 1–5 surfaced a concrete need for one, and a client's per-project curation (Deliverable 5) would become an actual confidentiality problem if analytics were ever aggregated across a GC's whole project book (ADR-057). Recorded as a considered decision, not a silent omission.
- [x] **Tests (Deliverable 7):** `tests/test_api_analytics.py` extended from 8 to 22 tests — new aggregation math, tenant isolation for every new field, the nullable-`osha_recordable` boundary, NULL-completion-percent exclusion. `frontend/src/components/AnalyticsPanel.test.tsx` extended from 6 to 25 tests, including dedicated client-vs-staff RBAC coverage. Full suite: **1081 backend passed, 116 frontend passed, 0 skipped, 0 regressions.**
- [x] A real pre-existing test gap surfaced and fixed along the way: `DashboardPage.test.tsx` rendered `AnalyticsPanel` without an `AuthProvider` ancestor — invisible until Deliverable 5 made `AnalyticsPanel` call `useAuth()` for the first time. Fixed by wrapping `renderDashboard()` in `AuthProvider`, matching `DocumentsPanel.test.tsx`'s existing pattern.
- [x] A real frontend robustness gap surfaced live (not by a unit test) and fixed: all four of this sprint's new response arrays were mapped over unconditionally; a response missing one (observed against a stale backend process during verification) threw uncaught and unmounted the whole dashboard, not just the Analytics card. Guarded with `?? []` on all four.
- [x] No Sprint 1–12 code modified except additive extensions (new response fields, new repository methods, one extracted shared helper) — no rewrites.
- [x] No placeholder code, no TODO stubs, no incomplete implementations.

**Sprint 13 Status: APPROVED & FROZEN** (approved 2026-09-16)

## Next Actions

1. ~~Approve Sprint 8~~ — **done 2026-08-19**, after the post-Sprint-8 fixes above (especially the Groq model migration) were verified live against real Groq, since Sprint 8's own test run never actually exercised a live LLM call.
2. ~~Approve Sprint 9~~ — **done 2026-08-19**, after all four deliverables were verified live (not just against the mock-based test suite): a real Celery worker via real Redis, a real emailed reset link, real Redis-backed rate-limit entries, and a full Playwright-driven browser session against the real running backend.
3. ~~Approve Sprint 10~~ — **done 2026-09-15**, after independent live re-verification during the resume audit (see note above).
4. ~~Approve Sprint 11~~ — **done 2026-09-16**, after the post-resume-audit backlog cleanup above was verified live.
5. ~~Approve Sprint 12~~ — **done 2026-09-16**, after all 7 deliverables were verified live, including a real Playwright browser session for the frontend panel.
6. ~~Approve Sprint 13~~ — **done 2026-09-16**, after all 7 deliverables were verified live, including a real client-role browser login for Deliverable 5's curation check.
7. **Begin Sprint 14 — Cost Intelligence**, per `docs/ROADMAP.md`'s Phase 4 plan and the spec now in `docs/NEXT_SPRINT.md`.
