# PROJECT STATE — Construction Site AI

**Primary project state document. Updated at end of every sprint.**
**Note:** The root-level `PROJECT_STATE.md` is a frozen Sprint 1 artifact. This file is the evolving, canonical state.

---

## Current Status

| Field | Value |
|-------|-------|
| Current Sprint | Sprint 2 — COMPLETE & PENDING APPROVAL |
| Next Sprint | Sprint 3 — Awaiting Sprint 2 Approval |
| Sprint 2 Status | COMPLETE — Pending user review and approval |
| Last Updated | 2026-06-30 |
| Schema Version | ConstructionDailyLog v1.0.0 |
| Codebase | Knowledge base + Data generation framework. Zero application code. Zero database. |

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
│   ├── NEXT_SPRINT.md                     ✅ Sprint 2 preparation (new)
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
├── requirements-dev.txt                       ✅ SPRINT 2 — Dev dependencies
│
backend/            ← Sprint 7+ (not yet created)
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
| Faster Whisper (base) | Open source, local | Speech-to-text | Sprint 3 | Free |
| Qwen2.5 7B Instruct | Alibaba, via Ollama | Information extraction | Sprint 4 | Free |
| Qwen2.5 7B Instruct | Alibaba, via Ollama | Report/email generation | Sprint 5 | Free |

All models run locally. No API keys required. No cloud costs.

---

## Database Status

No database created. Planned for Sprint 6.

**Planned tables (subject to Sprint 6 design):**
`users`, `companies`, `projects`, `sites`, `workers`, `trades`, `daily_logs`, `audio_files`, `work_items`, `materials_used`, `materials_delivered`, `materials_required`, `equipment_used`, `safety_incidents`, `safety_hazards`, `delays`, `inspections`, `attachments`, `ai_generated_outputs`, `audit_logs`

---

## Datasets Status

| Dataset | Sprint | Status | Location |
|---------|--------|--------|----------|
| Construction stages knowledge | 1 | ✅ Done | `knowledge/construction_stages.json` |
| ConstructionDailyLog schema | 1 | ✅ Done | `knowledge/construction_daily_log_schema.json` |
| Construction rules | 1.1 | ✅ Done | `knowledge/construction_rules.json` |
| Validation rules | 1.1 | ✅ Done | `knowledge/validation_rules.json` |
| Daily site logs (5,000) | 2 | Pending | `datasets/daily_logs/` |
| Safety toolbox talks | 2 | Pending | `datasets/safety_talks/` |
| Material database (~500) | 2 | Pending | `datasets/materials/` |
| Customer progress examples (1,000) | 2 | Pending | `datasets/customer_updates/` |
| Project schedules (1,000) | 2 | Pending | `datasets/schedules/` |

---

## Key Technical Decisions (Summary)

| # | Decision | Choice | Reason |
|---|----------|--------|--------|
| ADR-001 | Schema format | JSON Schema draft-07 | Language-agnostic, generates Pydantic+TypeScript |
| ADR-002 | Primary keys | UUID v4 | Security, offline generation, no collisions |
| ADR-003 | Null handling | Explicit `["type","null"]` | Distinguish AI-null from schema-missing |
| ADR-004 | Schema organization | 12 sections | Maps to DB tables, AI prompt sections |
| ADR-005 | AI runtime | 100% local (Ollama) | No cost, privacy, no vendor lock |
| ADR-006 | Knowledge format | JSON files | Version control, AI-friendly, no DB required |
| ADR-007 | Training data | Synthetic generation | No public dataset exists |
| ADR-008 | Stage granularity | 22 enum values | More granular than 11 phases |

---

## Known Issues and Limitations

| Issue | Severity | Resolution Plan |
|-------|----------|----------------|
| Schema is English-only | Medium | Future sprint: multi-language field support |
| USA-centric standards (OSHA, IRC) | Low | Future: international standards module |
| No validation tooling yet (Python) | Medium | Sprint 4: Python validator consuming validation_rules.json |
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

---

## Next Actions

1. **Owner action required:** Review Sprint 1 deliverables and approve
2. **After approval:** Sprint 2 begins — Synthetic Dataset Generation
3. **Sprint 2 lead time:** Python 3.12 environment needed. Run: `pip install jsonschema faker pytest`
