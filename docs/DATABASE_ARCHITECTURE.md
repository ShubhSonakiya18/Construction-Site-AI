# Database Architecture — Construction Site AI

Sprint 6 · Last Updated: 2026-07-10

---

## 1. Overview

The Construction Site AI persistence layer is a PostgreSQL database managed via SQLAlchemy 2.x ORM and Alembic migrations. It stores data for a **multi-company SaaS** platform: voice recordings from construction sites flow through speech transcription → AI extraction → daily log storage → AI report generation.

**26 tables** across 7 logical groups:

| Group | Tables | Purpose |
|---|---|---|
| Reference | 4 | Lookup enums (trades, stages, materials, PPE) |
| Company/Auth | 2 | Multi-tenancy root + user accounts |
| Workers | 1 | People who appear on sites |
| Projects | 3 | Project hierarchy + assignments |
| Audio Pipeline | 2 | Audio files + speech transcripts |
| Daily Logs | 12 | Core daily log + 11 normalized child tables |
| Generation | 2 | AI output storage + audit trail |

---

## 2. ER Diagram (ASCII)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ REFERENCE TABLES (lookup/enum, no FKs)                                     │
├──────────────┬──────────────────────┬───────────────────┬───────────────────┤
│ trades       │ construction_stages  │ material_categories│ ppe_types        │
│ ─────────── │ ─────────────────── │ ─────────────────│ ────────────────  │
│ id (PK)      │ id (PK)              │ id (PK)           │ id (PK)           │
│ code UNIQUE  │ code UNIQUE          │ code UNIQUE       │ code UNIQUE       │
│ display_name │ display_name         │ display_name      │ display_name      │
│ is_licensed  │ sequence_order       │ description       │ osha_reference    │
└──────────────┴──────────────────────┴───────────────────┴───────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│ COMPANY / AUTH                                                        │
│                                                                       │
│  companies ◄─────────────────────────────── users                    │
│  ──────────                                 ──────                    │
│  id (PK)                                    id (PK)                  │
│  slug UNIQUE                                company_id → companies    │
│  subscription_tier                          email UNIQUE              │
│  [SoftDelete] [AuditUser]                   role                      │
│                                             worker_id → workers (opt) │
│                                             [SoftDelete] [AuditUser]  │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│ WORKERS (belong to a company)                                         │
│                                                                       │
│  workers                                                              │
│  ───────                                                              │
│  id (PK)                                                              │
│  company_id → companies  [RESTRICT]                                   │
│  trade_id   → trades     [SET NULL]                                   │
│  user_id    → users      [SET NULL, optional]                        │
│  first_name, last_name, role                                          │
│  [SoftDelete] [AuditUser]                                             │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│ PROJECTS                                                              │
│                                                                       │
│  companies ──< projects ──< sites                                    │
│                    │                                                   │
│                    └──< project_workers >── workers                   │
│                                                                       │
│  projects                    sites              project_workers       │
│  ────────                    ─────              ───────────────       │
│  id (PK)                     id (PK)            id (PK)              │
│  company_id [RESTRICT]       project_id [CASCADE]  project_id [CASCADE]│
│  name, status                address, is_primary  worker_id [CASCADE]│
│  [SoftDelete] [AuditUser]                       UNIQUE(project, worker)│
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│ AUDIO PIPELINE                                                        │
│                                                                       │
│  audio_files ──1── speech_transcripts                                 │
│  ───────────         ──────────────────                               │
│  id (PK)             id (PK)                                          │
│  project_id [SET NULL]   audio_file_id → audio_files [CASCADE,UNIQUE] │
│  processing_status       raw_text, avg_confidence                    │
│  original_filename       segments (JSON — Whisper segment array)     │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│ DAILY LOGS (core entity)                                              │
│                                                                       │
│  daily_logs                                                           │
│  ──────────                                                           │
│  id (PK)                                                              │
│  project_id → projects   [RESTRICT]                                   │
│  site_id    → sites      [SET NULL]                                   │
│  audio_file_id→audio_files[SET NULL, UNIQUE — 1 log per recording]   │
│  foreman_id → workers    [SET NULL]                                   │
│  log_date, review_status, current_stage                               │
│  raw_transcript*, transcript_confidence*   ← ADR-027 denormalization │
│  weather, late_arrivals, absences, visitors (JSON blobs — ADR-028)   │
│  UNIQUE(project_id, log_date)                                         │
│  [SoftDelete] [AuditUser]                                             │
│       │                                                               │
│       │ CASCADE DELETE to all 11 child tables below                   │
│       ▼                                                               │
│  ┌──────────────────┬──────────────────┬────────────────────────┐    │
│  │ log_trades_on_   │ log_work_items   │ log_work_in_progress   │    │
│  │ site             │                  │                         │    │
│  ├──────────────────┼──────────────────┼────────────────────────┤    │
│  │ log_materials_   │ log_materials_   │ log_materials_         │    │
│  │ used             │ delivered        │ required               │    │
│  ├──────────────────┼──────────────────┼────────────────────────┤    │
│  │ log_equipment    │ log_safety_      │ log_hazards            │    │
│  │                  │ incidents        │                         │    │
│  ├──────────────────┼──────────────────┼────────────────────────┤    │
│  │ log_delays       │ log_inspections  │                         │    │
│  └──────────────────┴──────────────────┴────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│ GENERATION / AUDIT                                                    │
│                                                                       │
│  daily_logs ──< generation_outputs          audit_logs               │
│                  ──────────────────          ──────────               │
│                  id (PK)                     id (PK)                 │
│                  daily_log_id [SET NULL]     created_at ONLY         │
│                  service_type               (immutable — no updates)  │
│                  generation_id (UUID corr.) event_type               │
│                  content (TEXT)             entity_type, entity_id   │
│                  UNIQUE(log_id,service,run)  actor_id, company_id    │
│                                             old_values/new_values    │
│                                             event_metadata (JSON)    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Design Decisions (ADRs)

### ADR-002: UUID v4 Primary Keys Everywhere
**Decision**: All tables use `UUID` primary keys, not auto-increment integers.  
**Why**: The ConstructionDailyLog JSON schema uses UUIDs. Consistent UUID PKs mean IDs from extraction JSON map directly to database IDs without translation. Distributed inserts (future multi-region) never collide.  
**Consequence**: Joins are slightly slower; index pages are larger. Acceptable for this domain.

### ADR-026: AuditUserMixin Without FK Constraints
**Decision**: `created_by_id` and `updated_by_id` columns are plain UUID columns with NO FK constraints to the `users` table.  
**Why**: `companies.created_by_id` would reference `users.id`, but `users.company_id` references `companies.id`. This circular FK dependency cannot be resolved with RESTRICT/CASCADE semantics and would prevent dropping either table in migrations.  
**How**: Enforced at application layer: service code validates actor IDs exist before persisting. The FK is "logical" not "physical".

### ADR-027: Denormalized Transcript Data on DailyLog
**Decision**: `daily_logs.raw_transcript` and `daily_logs.transcript_confidence` are denormalized copies of data from `speech_transcripts`.  
**Why**: The Sprint 7 daily-log detail API needs both the extracted log data AND the original transcript for display in the UI. Without denormalization, every API response requires a 3-table join: `daily_logs → audio_files → speech_transcripts`. With denormalization, the join is eliminated for the 99% case.  
**Risk**: Transcript data can diverge if re-transcription happens. Acceptable: raw_transcript is append-only in practice.

### ADR-028: JSON Blobs vs. Child Tables
**Decision**: Some arrays are stored as JSON columns on `daily_logs`; others are normalized into child tables.  
**Rule applied**:
- **JSON blob**: arrays that are *always fetched together* and *never queried individually* — `weather`, `late_arrivals`, `absences`, `visitors`, `safety_meeting_topics`, `ppe_required_today`, `tomorrow_plan`, `client_communication`, `attachments`, `financials`
- **Child table**: arrays where *individual rows are independently queryable* — trades on site, work items, materials, equipment, hazards, incidents, delays, inspections  
**Why**: Normalizing arrays that are always fetched whole adds JOIN overhead without query benefit. Normalizing arrays that PM dashboards filter (e.g., "all OSHA-recordable incidents this week") enables proper indexing.

### ADR-029: Soft Delete Pattern
**Decision**: Mutable business entities use soft delete (`deleted_at` timestamp) rather than hard delete.  
**Why**: Construction foremen sometimes delete a log by mistake. Soft delete enables recovery. `list()` queries always filter `WHERE deleted_at IS NULL`.  
**Tables with soft delete**: companies, users, workers, projects, daily_logs  
**Tables without soft delete**: reference tables (immutable), audio_files, speech_transcripts, generation_outputs, audit_logs

### ADR-030: AuditLog Immutability
**Decision**: `AuditLog` rows are never updated or deleted.  
**Why**: An audit trail that can be modified isn't an audit trail. Compliance requirements (OSHA, general contractor insurance) demand tamper-evident logs.  
**Implementation**: `AuditLog` model has no `TimestampMixin` (no `updated_at`), no `SoftDeleteMixin`. Only `UUIDPrimaryKeyMixin` + explicit `created_at` with `server_default=func.now()`.

---

## 4. Table Reference

### Reference Tables

| Table | Rows | Description |
|---|---|---|
| `trades` | 25 | Construction trade disciplines (carpenter, electrician, plumber…) |
| `construction_stages` | 22 | Project phases in sequence order (foundation→framing→…→closeout) |
| `material_categories` | 16 | Material classification (lumber, concrete, electrical…) |
| `ppe_types` | 16 | Required PPE types with OSHA references |

All reference tables: `code VARCHAR(50) UNIQUE`, `display_name`, `is_active`, timestamps.

### Daily Log Review Lifecycle

```
draft → [submit_for_review] → under_review → [approve] → approved
                                           → [reject]  → rejected
rejected → [resubmit] → under_review → ...
```

Review status is stored in `daily_logs.review_status` (VARCHAR(30)).

### Mixin Composition

Every ORM model uses 1-4 composable mixins:

| Mixin | Adds | Used On |
|---|---|---|
| `UUIDPrimaryKeyMixin` | `id UUID PK` | All 26 tables |
| `TimestampMixin` | `created_at`, `updated_at` | All except AuditLog |
| `SoftDeleteMixin` | `deleted_at`, `is_deleted` property | Company, User, Worker, Project, DailyLog |
| `AuditUserMixin` | `created_by_id`, `updated_by_id` (plain UUID, no FK) | Company, User, Worker, Project, DailyLog |

---

## 5. Repository Pattern

Every entity has a typed repository class. Business logic never touches `Session` directly.

```
database/repositories/
├── base.py          — BaseRepository[T] with generic CRUD
├── company.py       — CompanyRepository, UserRepository
├── project.py       — ProjectRepository, SiteRepository, ProjectWorkerRepository
├── worker.py        — WorkerRepository (find_by_name for voice extraction)
├── audio.py         — AudioRepository, SpeechTranscriptRepository
├── daily_log.py     — DailyLogRepository (create_from_extraction_result)
└── generation.py    — GenerationRepository, AuditLogRepository
```

**Key methods:**
- `DailyLogRepository.get_with_children(id)` — loads all 11 child tables via `selectinload()` to avoid N+1
- `DailyLogRepository.create_from_extraction_result(dict, project_id)` — Sprint 4→6 integration
- `GenerationRepository.create_from_service_output(log_id, output)` — Sprint 5→6 integration
- `AuditLogRepository.log_event(event_type, **kwargs)` — append-only audit write

---

## 6. Migration Guide

### Prerequisites

```bash
# PostgreSQL must be running
# DATABASE_URL must be set
export DATABASE_URL="postgresql://user:pass@localhost:5432/construction_site_ai"
```

### First-time Setup

```bash
# 1. Apply all migrations
alembic upgrade head

# 2. Seed reference data (25 trades, 22 stages, 16 categories, 16 PPE types)
python -c "
from database.session import get_session
from database.seed.reference_data import seed_all_reference_data
with get_session() as s:
    counts = seed_all_reference_data(s)
print(counts)
"

# 3. Seed sample data (dev only — creates one demo company + project + daily log)
python -c "
from database.session import get_session
from database.seed.reference_data import seed_all_reference_data
from database.seed.sample_data import seed_sample_data
with get_session() as s:
    seed_all_reference_data(s)
    seed_sample_data(s)
"
```

### Adding a Migration

```bash
# Auto-generate from model changes
alembic revision --autogenerate -m "add column X to table Y"

# Review the generated file in database/migrations/versions/
# Then apply
alembic upgrade head
```

### Rollback

```bash
# Rollback one migration
alembic downgrade -1

# Rollback to a specific revision
alembic downgrade 001
```

### Testing Without PostgreSQL

All ORM tests use SQLite in-memory. No PostgreSQL is required for `pytest`:

```bash
pytest tests/test_db_models.py tests/test_db_repositories.py tests/test_db_seed.py
```

SQLite compatibility notes:
- ORM models use generic `JSON` (not `JSONB`) — works on SQLite
- ORM models use `Uuid(as_uuid=True)` (not native PG UUID) — works on SQLite
- The Alembic migration uses PostgreSQL-native JSONB and UUID for production

---

## 7. Performance Indexes

Critical query indexes created in `001_initial_schema.py`:

| Index | Table | Columns | Query Pattern |
|---|---|---|---|
| `uq_daily_logs_project_date` | daily_logs | (project_id, log_date) | One log per project per day |
| `ix_daily_logs_project_date_status` | daily_logs | (project_id, log_date, review_status) | Dashboard: pending review |
| `ix_workers_company_id` | workers | (company_id) | List workers for company |
| `ix_generation_outputs_generation_id` | generation_outputs | (generation_id) | Sprint 5 correlation lookup |
| `ix_audit_logs_entity_type_id` | audit_logs | (entity_type, entity_id) | Audit trail per entity |
| `ix_audit_logs_created_at` | audit_logs | (created_at) | Time-range audit queries |

---

## 8. File Map

```
database/
├── __init__.py              # Re-exports Base, get_session, DatabaseConfig
├── base.py                  # DeclarativeBase — shared by all 26 models
├── config.py                # DatabaseConfig dataclass + from_env()
├── mixins.py                # 4 composable mixins (UUID, Timestamp, SoftDelete, AuditUser)
├── session.py               # get_engine() singleton, get_session() context manager
├── models/
│   ├── __init__.py          # Imports all 26 models — critical for Alembic
│   ├── reference.py         # Trade, ConstructionStage, MaterialCategory, PPEType
│   ├── company.py           # Company, User
│   ├── project.py           # Project, Site, ProjectWorker
│   ├── worker.py            # Worker
│   ├── audio.py             # AudioFile, SpeechTranscript
│   ├── daily_log.py         # DailyLog (12 JSON blobs + 11 child table relationships)
│   ├── log_items.py         # 11 normalized log child tables
│   └── generation.py        # GenerationOutput, AuditLog
├── repositories/
│   ├── __init__.py          # Re-exports all repository classes
│   ├── base.py              # BaseRepository[T] generic CRUD
│   ├── company.py           # CompanyRepository, UserRepository
│   ├── project.py           # ProjectRepository, SiteRepository, ProjectWorkerRepository
│   ├── worker.py            # WorkerRepository
│   ├── audio.py             # AudioRepository, SpeechTranscriptRepository
│   ├── daily_log.py         # DailyLogRepository
│   └── generation.py        # GenerationRepository, AuditLogRepository
├── seed/
│   ├── __init__.py
│   ├── reference_data.py    # Idempotent seed: 25 trades, 22 stages, 16 cats, 16 PPE
│   └── sample_data.py       # Fixed-UUID demo company + project + daily log
└── migrations/
    ├── __init__.py
    ├── env.py               # Alembic env: reads DATABASE_URL, imports all models
    ├── script.py.mako       # Template for new migration files
    └── versions/
        └── 001_initial_schema.py  # All 26 tables, PostgreSQL-native types
```
