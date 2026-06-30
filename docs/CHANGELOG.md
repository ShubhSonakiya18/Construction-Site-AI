# CHANGELOG

All notable changes to Construction Site AI are documented here.
Format: `[Sprint X] Date — Description`

---

## [Sprint 1.1] 2026-06-30 — Sprint 1 Freeze & Knowledge Base Extension

### Added
- `knowledge/construction_rules.json` — 38 machine-readable construction rules (sequential, parallel, material consistency, worker consistency, safety constraints, weather constraints, quantity sanity)
- `knowledge/dependency_graph.json` — Complete DAG of residential construction workflow with 23 nodes, 33 edges, critical path, parallel groups, and topological sort
- `knowledge/validation_rules.json` — 35 machine-readable validation rules with conditions, severities, error messages, and suggested fixes (consumed by Sprint 2 generators and Sprint 4 AI validator)
- `knowledge/construction_ontology.json` — Complete entity-relationship ontology covering trades, materials, equipment, hazards, PPE, worker roles, inspection types, delay types, and weather conditions with 40+ relationships. Designed for future RAG/FAISS integration
- `docs/CHANGELOG.md` — This file (project change history)
- `docs/DECISIONS.md` — Architecture decision record
- `docs/PROJECT_STATE.md` — Official project state (moved from root to docs/)
- `docs/NEXT_SPRINT.md` — Sprint 2 preparation document
- `docs/ROADMAP.md` — Full product roadmap
- `docs/HANDOVER.md` — Complete handover document for new sessions

### Fixed (Sprint 1 Gaps Identified)
- Gap: `construction_stages.json` covered only 11 stages but `current_stage` schema enum had 22 values. The ontology and dependency graph now cover all 22 stages.
- Gap: Sequencing rules were embedded inside `construction_stages.json` as a sub-object. Extracted to dedicated `construction_rules.json`.
- Gap: No machine-readable validation for dataset generators. Resolved with `validation_rules.json`.
- Gap: No entity-relationship model for future AI/RAG use. Resolved with `construction_ontology.json`.

---

## [Sprint 1.0] 2026-06-30 — Sprint 1 Initial Delivery

### Added
- `knowledge/construction_stages.json` — Knowledge base for all 11 residential construction stages with workers, materials, tools, delays, safety hazards, and daily report fields
- `knowledge/construction_daily_log_schema.json` — Master ConstructionDailyLog JSON Schema v1.0.0 with 12 sections, 80+ fields, UUID keys, explicit null typing, enum validation, and complete example
- `docs/sprint_1/CONSTRUCTION_RESEARCH.md` — Human-readable domain research on all 11 stages
- `docs/sprint_1/SCHEMA_DESIGN.md` — Architecture decisions explaining schema design choices
- `README.md` — Project overview with tech stack and sprint progress
- `.gitignore` — Python, Node, Docker, and AI model ignore rules
- `.env.example` — Complete environment variable template for all future modules
- `PROJECT_STATE.md` (root) — Sprint 1 state document (frozen as Sprint 1 artifact)

---

## [Sprint 2.0] 2026-06-30 — Synthetic Construction Data Generation Framework

### Added

#### Framework Infrastructure
- `dataset_generation_framework/` — Production-grade, reusable data generation framework
- `dataset_generation_framework/config.py` — Single source of truth for all generation parameters. Change 5 size constants to scale from 5,000 to 500,000+ records.
- `dataset_generation_framework/core/knowledge_loader.py` — Singleton KnowledgeBase with O(1) lookup indexes for all 6 Sprint 1 knowledge files
- `dataset_generation_framework/core/stage_machine.py` — DAG-based construction project state machine (ProjectState + StageMachine). Enforces topological stage ordering from `dependency_graph.json`
- `dataset_generation_framework/core/rule_engine.py` — Query interface for `construction_rules.json`. Answers questions like "Can roofing and HVAC run in parallel?" and "What materials are expected for framing?"
- `dataset_generation_framework/validation/pipeline.py` — 4-phase ValidationPipeline (blocking → errors → warnings → info). Fail-fast on Phase 1.
- `dataset_generation_framework/generators/base_generator.py` — Abstract `BaseGenerator` with streaming yield, seeded RNG, and `GeneratorStats` tracking
- `dataset_generation_framework/exporters/jsonl_exporter.py` — Batched JSONL file writer with context manager API
- `dataset_generation_framework/exporters/csv_exporter.py` — Batched CSV writer with auto-inferred headers, None→"", list→";" conversion
- `dataset_generation_framework/statistics/report_generator.py` — Post-generation statistical analysis and summary report

#### Dataset Generators
- `dataset_generation_framework/generators/daily_log_generator.py` — Simulates complete construction projects day-by-day to produce `ConstructionDailyLog` records. Uses StageMachine + RuleEngine to guarantee sequencing correctness.
- `dataset_generation_framework/generators/schedule_generator.py` — Generates project schedules with planned vs. actual dates and delay breakdown
- `dataset_generation_framework/generators/safety_talk_generator.py` — Generates safety toolbox talk records from OSHA knowledge and ontology hazards
- `dataset_generation_framework/generators/material_generator.py` — Generates construction material catalog entries from ontology
- `dataset_generation_framework/generators/customer_update_generator.py` — Generates (raw foreman notes, customer email) training pairs

#### Entry Point
- `generate.py` — CLI entry point: `python generate.py`, `python generate.py --dataset daily_logs --count 5000 --seed 42`

#### Tests
- `tests/test_knowledge_loader.py` — Unit tests for KnowledgeBase singleton, all API domains
- `tests/test_stage_machine.py` — Unit tests for StageMachine, ProjectState, can_start(), advance_day()
- `tests/test_validation_pipeline.py` — Unit tests for ValidationResult, 4-phase pipeline, all rule types
- `tests/test_generators.py` — Unit tests for all 5 generators (count, keys, range validation, reproducibility)
- `tests/test_integration.py` — End-to-end pipeline tests (generator → exporter → file → read-back validation)

#### Dataset Infrastructure
- `datasets/raw/`, `datasets/generated/`, `datasets/validated/`, `datasets/exports/` — Dataset directory structure
- `datasets/README.md` — Dataset documentation: format, schema, purpose, generation commands
- `requirements-dev.txt` — Python development dependencies (jsonschema, faker, pytest, pytest-cov, tqdm)

### Architecture Decisions (Sprint 2)
- ADR-009: Production framework architecture over one-off scripts (see DECISIONS.md)
- ADR-010: Project simulation over random record generation (see DECISIONS.md)
- ADR-011: Streaming generators — same peak memory at 500k as at 5k (see DECISIONS.md)
