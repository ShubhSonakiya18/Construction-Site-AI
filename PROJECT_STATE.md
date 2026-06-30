# PROJECT STATE — Construction Site AI

**Single source of truth for project status.**
Updated at the end of every sprint.

---

## Current Sprint

**Sprint 1 — Construction Research + Schema Design**
**Status:** COMPLETE — Awaiting Approval
**Completed:** 2026-06-30

---

## Repository Overview

```
Construction-Site-AI/
│
├── knowledge/
│   ├── construction_stages.json            ✅ Sprint 1
│   └── construction_daily_log_schema.json  ✅ Sprint 1
│
├── docs/
│   └── sprint_1/
│       ├── CONSTRUCTION_RESEARCH.md        ✅ Sprint 1
│       └── SCHEMA_DESIGN.md               ✅ Sprint 1
│
├── README.md                               ✅ Sprint 1
├── .gitignore                              ✅ Sprint 1
├── .env.example                            ✅ Sprint 1
└── PROJECT_STATE.md                        ✅ Sprint 1
```

---

## Sprint History

### Sprint 1 — Construction Research + Schema Design ✅

**Goal:** Build the domain knowledge foundation and design the master data schema.

**Deliverables:**

| Deliverable | File | Status |
|-------------|------|--------|
| 11 construction stages knowledge base | `knowledge/construction_stages.json` | ✅ Complete |
| Master ConstructionDailyLog schema | `knowledge/construction_daily_log_schema.json` | ✅ Complete |
| Construction research documentation | `docs/sprint_1/CONSTRUCTION_RESEARCH.md` | ✅ Complete |
| Schema design decisions | `docs/sprint_1/SCHEMA_DESIGN.md` | ✅ Complete |
| Project README | `README.md` | ✅ Complete |
| Git ignore | `.gitignore` | ✅ Complete |
| Environment template | `.env.example` | ✅ Complete |

---

## Completed Features

### Knowledge Base
- All 11 residential construction stages documented
- Per-stage: purpose, duration, workers, materials, tools, delays, safety hazards, daily report fields
- Construction sequencing rules (hard rules + parallel-allowed rules)
- Worker roles, license requirements, typical counts per trade
- Weather sensitivity matrix for all stages
- OSHA references for critical hazards

### Master Schema (ConstructionDailyLog v1.0.0)
- 12 logical sections covering the full lifecycle of a daily log
- JSON Schema draft-07 compliant
- All required fields marked
- All nullable fields explicitly typed as `["type", "null"]`
- UUID primary keys throughout
- Enum values for all categorical fields
- Full example document with real data
- AI output sections pre-designed for all 5 AI services
- Forward-compatibility fields for future modules (Defect Detection, Cost Tracking, Scheduling)
- Schema versioning for future migrations

---

## Pending Features (Future Sprints)

| Feature | Sprint | Status |
|---------|--------|--------|
| Synthetic dataset generation (5 datasets) | Sprint 2 | Not started |
| Speech-to-Text pipeline (Faster Whisper) | Sprint 3 | Not started |
| Information Extraction Engine (Qwen2.5) | Sprint 4 | Not started |
| AI Services (5 generators) | Sprint 5 | Not started |
| PostgreSQL database design | Sprint 6 | Not started |
| FastAPI backend | Sprint 7+ | Not started |
| React frontend | Future | Not started |
| JWT Authentication | Future | Not started |
| Docker deployment | Future | Not started |
| Defect Detection | Future | Not started |
| Analytics Dashboard | Future | Not started |

---

## Database Status

**No database yet.** Database design is Sprint 6.

The `ConstructionDailyLog` schema (Sprint 1) will directly inform the database table design. Every section of the schema maps to one or more normalized tables.

Planned tables (preliminary, Sprint 6 will finalize):
- `users`
- `companies`
- `projects`
- `sites`
- `workers`
- `daily_logs`
- `audio_files`
- `work_items`
- `materials_used`
- `materials_delivered`
- `safety_incidents`
- `delays`
- `inspections`
- `ai_generated_outputs`
- `audit_logs`

---

## AI Models Planned

| Model | Purpose | Sprint |
|-------|---------|--------|
| Faster Whisper (base/small) | Speech-to-text | Sprint 3 |
| Qwen2.5 7B Instruct (via Ollama) | Information extraction | Sprint 4 |
| Qwen2.5 7B Instruct (via Ollama) | Report generation | Sprint 5 |

All models run **locally**. No external API calls. No API keys required.

---

## Datasets Created

| Dataset | Status | Location |
|---------|--------|----------|
| Construction stages knowledge | ✅ Sprint 1 | `knowledge/construction_stages.json` |
| Daily log schema | ✅ Sprint 1 | `knowledge/construction_daily_log_schema.json` |
| Daily site logs (5,000 synthetic) | Sprint 2 | `datasets/daily_logs/` |
| Safety toolbox talks | Sprint 2 | `datasets/safety_talks/` |
| Material database | Sprint 2 | `datasets/materials/` |
| Customer progress examples | Sprint 2 | `datasets/customer_updates/` |
| Project schedules | Sprint 2 | `datasets/schedules/` |

---

## Technical Decisions Log

| Decision | Chosen | Reason | Sprint |
|----------|--------|--------|--------|
| Schema format | JSON Schema draft-07 | Language-agnostic, auto-generates Pydantic and TypeScript | 1 |
| ID format | UUID | Security, offline generation, multi-DB merge safety | 1 |
| Null handling | Explicit `["type", "null"]` | Distinguish null vs missing in AI outputs | 1 |
| Schema structure | 12 sections | One section per concern, maps to database tables | 1 |
| Knowledge base format | JSON | Machine-readable, AI-consumable | 1 |
| Stage sequencing | Hard rules in JSON | AI validation of realistic logs | 1 |

---

## Known Issues and Limitations

### Sprint 1 Limitations
1. **No validation tooling yet** — The JSON schema exists but no Python validator has been written yet (Sprint 4 will add this).
2. **Schema is English-only** — Multi-language support for voice notes in Spanish, Portuguese, etc. is not yet designed.
3. **Residential scope only** — The construction stages are designed for residential single-family construction. Commercial construction has different stages, trades, and inspection requirements.
4. **USA-centric** — OSHA references, IRC codes, and inspection processes are USA-specific. International adaptation is a future consideration.
5. **Manual weather entry** — Weather fields are populated by AI extraction from voice. Auto-fetching from weather API is not yet designed.

---

## Next Sprint Goals (Sprint 2)

Sprint 2: Synthetic Dataset Generation

**Goal:** Generate 5 realistic synthetic datasets that will be used for:
- Testing the Information Extraction Engine (Sprint 4)
- Testing the AI Services (Sprint 5)
- Fine-tuning and evaluation

**Datasets to Generate:**

1. **Daily Site Logs** — 5,000 synthetic logs in ConstructionDailyLog format
   - Realistic sequencing (painting never before drywall)
   - Realistic weather patterns (rain not every day)
   - Material quantities that match the stage
   - Worker counts that match the trade

2. **Safety Toolbox Talks** — Based on OSHA public domain documents
   - CSV format with trade, hazard, PPE, quiz questions

3. **Material Database** — ~500 construction materials
   - With categories, units, suppliers, lead times

4. **Customer Progress Examples** — 1,000 technical-to-professional email pairs
   - JSONL format for few-shot learning

5. **Project Schedules** — 1,000 residential construction schedules
   - With dependencies, weather delays, completion percentages

**Key Engineering Work:**
- Python generator scripts (not manually created data)
- Reproducible with random seed
- Validation that generated data conforms to ConstructionDailyLog schema
- Dataset versioning

---

## Environment Requirements (Current Sprint)

No environment setup required for Sprint 1. All deliverables are JSON and Markdown files.

Sprint 3 will introduce the first software requirements:
- Python 3.12
- Faster Whisper
- Ollama
- Docker

---

*Last updated: Sprint 1 completion — 2026-06-30*
