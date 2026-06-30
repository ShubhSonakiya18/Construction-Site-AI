# HANDOVER — Construction Site AI

**Purpose:** This document allows any future Claude Code session to immediately understand the project state, architecture, and next steps without reading the entire conversation history.

**Last Updated:** 2026-06-30
**Handover Status:** Sprint 1 COMPLETE — Awaiting Owner Approval for Sprint 2

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
- NO paid APIs (no OpenAI, no Claude API, no Gemini, no Azure AI, no AWS AI)
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
| Completed Sprint | Sprint 1 — COMPLETE & FROZEN |
| Sprint 1 Scope | Construction research + Knowledge base + Schema design |
| Next Sprint | Sprint 2 — Synthetic Dataset Generation |
| Sprint 2 Status | **BLOCKED — Awaiting Sprint 1 Owner Approval** |
| Schema Version | ConstructionDailyLog v1.0.0 (FROZEN) |

**If this session is continuing after Sprint 1 approval:** Read `docs/NEXT_SPRINT.md` for complete Sprint 2 specification before writing any code.

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
│   ├── NEXT_SPRINT.md                           Sprint 2 full spec
│   ├── ROADMAP.md                               Full product roadmap
│   └── HANDOVER.md                              This file
│
├── README.md
├── .gitignore
├── .env.example
└── PROJECT_STATE.md                             FROZEN Sprint 1 root artifact
```

**NOT YET CREATED (future sprints):**
- `datasets/` — Sprint 2
- `scripts/` — Sprint 2
- `tests/` — Sprint 2
- `backend/` — Sprint 7+
- `frontend/` — Sprint 9+

---

## 5. Architecture Status

### AI Stack (Planned, Not Yet Implemented)

| Component | Technology | Purpose | Sprint |
|-----------|-----------|---------|--------|
| Speech-to-text | Faster Whisper (local) | Audio → transcript | Sprint 3 |
| Language model | Qwen2.5 7B via Ollama (local) | Extraction + generation | Sprint 4-5 |
| Vector store | FAISS (local) | RAG from knowledge base | Future |

### Backend Stack (Planned, Not Yet Implemented)

| Component | Technology | Sprint |
|-----------|-----------|--------|
| API framework | FastAPI | Sprint 7 |
| ORM | SQLAlchemy | Sprint 6 |
| Database | PostgreSQL | Sprint 6 |
| Task queue | Celery + Redis | Sprint 7 |
| Authentication | JWT | Sprint 8 |

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

## 8. Sprint 2 Summary (What to Build Next)

Full spec is in `docs/NEXT_SPRINT.md`. Summary:

**5 datasets, 5 generators (Python), tests:**

| Dataset | Count | Format | Generator |
|---------|-------|--------|-----------|
| Daily site logs | 5,000 | JSONL | `generate_daily_logs.py` |
| Safety toolbox talks | ~200 | CSV | `generate_safety_talks.py` |
| Material database | ~500 | CSV | `generate_materials.py` |
| Customer progress updates | 1,000 | JSONL | `generate_customer_updates.py` |
| Project schedules | 1,000 | JSONL | `generate_schedules.py` |

**Key generator constraints:**
- All generators must accept `--seed` for reproducibility
- All generators validate output against `knowledge/validation_rules.json`
- All generators load rules from `knowledge/` files, never hardcode rules
- Daily logs must follow sequencing from `knowledge/dependency_graph.json`
- Stage enum must use 22-value enum from schema (not 11-stage research groupings)

**Python packages needed:** `jsonschema`, `faker`, `pytest`

**New folders for Sprint 2 only:** `datasets/`, `scripts/generators/`, `tests/`

---

## 9. Sprint Roadmap (Full)

| Sprint | Phase | Goal | Status |
|--------|-------|------|--------|
| 1 | Core AI Pipeline | Knowledge base + Schema | ✅ FROZEN |
| 2 | Core AI Pipeline | Synthetic datasets | Pending approval |
| 3 | Core AI Pipeline | Faster Whisper STT | Not started |
| 4 | Core AI Pipeline | AI extraction (Qwen2.5) | Not started |
| 5 | Core AI Pipeline | AI generation services (5 outputs) | Not started |
| 6 | Core AI Pipeline | PostgreSQL schema + Alembic | Not started |
| 7 | Backend API | FastAPI + Celery | Not started |
| 8 | Backend API | Auth + multi-tenancy | Not started |
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
| No Python validation tooling yet | Medium | Sprint 4 will build Python validator |
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

**7. No Docker until Sprint 7.**
Sprint 2 is pure Python. Sprint 3 adds Ollama (if available locally). Docker Compose comes in Sprint 7. Never add Docker configuration to a sprint that doesn't require it.

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

## 13. Environment Setup (When Starting Sprint 2)

```bash
# Python 3.12 required
python --version

# Install Sprint 2 dependencies
pip install jsonschema faker pytest

# Directory should be the project root
# All generators use relative paths like: "knowledge/construction_stages.json"
```

No Docker. No virtual environment required (though recommended). No `.env` file needed for Sprint 2 (generators don't touch a database or API).
