# Next Sprint: Sprint 2 — Synthetic Dataset Generation

**Status:** READY FOR IMPLEMENTATION — Pending Sprint 1 Approval
**Prerequisites:** Sprint 1 APPROVED and FROZEN
**Estimated Duration:** 3–5 days of implementation

---

## Objectives

Sprint 2 generates the training and test data that every future sprint depends on:
- Sprint 4 (AI Extraction) needs example logs to test extraction accuracy
- Sprint 5 (AI Services) needs example inputs and expected outputs to verify generator quality
- Future fine-tuning needs structured training pairs (transcript → log)

**No public dataset exists for construction daily logs.** We generate all data synthetically using rules from Sprint 1 knowledge base.

---

## Learning Goals (For Junior Engineers)

1. **Why synthetic data?** — Understand when real data is unavailable, too private, or too expensive to collect.
2. **What makes a good dataset?** — Diversity, realism, edge cases, balance, and reproducibility.
3. **Rule-based generation vs ML generation** — We use rule-based (Sprint 1 rules) not AI-generated data, because AI-generated training data creates circular validation problems.
4. **Data versioning** — Why datasets need version numbers like software.
5. **Validation** — Every generated record must pass `validation_rules.json` before being saved.

---

## Deliverables

### Dataset 1: Daily Site Logs
**File:** `datasets/daily_logs/daily_logs_v1.jsonl`
**Count:** 5,000 records
**Format:** JSONL (one JSON object per line, each conforming to `ConstructionDailyLog` schema v1.0.0)
**Generator:** `scripts/generators/generate_daily_logs.py`

**What the generator must produce:**
- Logs from 50 simulated projects (100 logs each)
- Each project follows a realistic construction sequence using `dependency_graph.json`
- Each log follows sequencing rules from `construction_rules.json`
- Weather generated probabilistically (rain max 25% frequency)
- Material quantities match the stage (concrete during foundation, not during painting)
- Worker counts follow trade-typical ranges from `construction_stages.json`
- Approximately 10% of logs include delays (realistic rate)
- Approximately 5% of logs include inspection entries
- Approximately 2% of logs include safety incidents

**Realism constraints:**
- Stage cannot go backward without a rework delay
- Painting never before drywall
- Material usage matches stage (enforced by `validation_rules.json` rules)
- Rain does not occur every day
- Project duration reflects real construction timelines

**Generator requirements:**
- Accepts `--seed` argument for reproducibility
- Accepts `--count` argument for number of projects
- Validates every record against `validation_rules.json` before writing
- Writes output to JSONL (streaming, not loading everything into memory)
- Logs generator statistics at end (records generated, validation failures, stage distribution)

---

### Dataset 2: Safety Toolbox Talks
**File:** `datasets/safety_talks/safety_talks_v1.csv`
**Count:** ~200 entries
**Format:** CSV
**Generator:** `scripts/generators/generate_safety_talks.py`
**Source:** OSHA public domain documents (osha.gov — all public domain)

**Columns:**
- `trade` — Which trade this talk is for
- `stage` — Which construction stage
- `hazard_type` — Hazard category from ontology
- `hazard_name` — Specific hazard
- `ppe_required` — List of required PPE
- `common_accidents` — Description of common accidents involving this hazard
- `dos` — What workers should do
- `donts` — What workers should NOT do
- `quiz_question_1` through `quiz_question_3` — Multiple choice quiz questions
- `correct_answer_1` through `correct_answer_3` — Correct option index (0-3)
- `osha_reference` — Specific OSHA standard
- `duration_minutes` — Estimated talk duration
- `language` — `en` (English only for Sprint 2; Spanish in future)
- `priority` — `high`/`medium`/`low` based on fatality statistics

**Source strategy:** Extract content from OSHA 10 and OSHA 30 construction safety topics. All OSHA content is US government public domain.

---

### Dataset 3: Material Database
**File:** `datasets/materials/materials_v1.csv`
**Count:** ~500 materials
**Format:** CSV
**Generator:** `scripts/generators/generate_materials.py`

**Columns:**
- `material_id` — UUID
- `material_name` — Standard procurement name
- `category` — Category enum (concrete, lumber, electrical, etc.)
- `trade` — Which trade uses this material
- `typical_stages` — Comma-separated list of stages where this material is used
- `typical_unit` — cubic_yards, sq_feet, linear_feet, sheets, gallons, each, bags, rolls
- `lead_time_days` — Procurement lead time
- `min_stock_level` — Minimum recommended stock (in typical_unit)
- `max_stock_level` — Maximum recommended stock
- `storage_conditions` — How to store this material on site
- `alternative_materials` — Comma-separated alternative material names
- `typical_cost_low_usd` — Low end cost per unit
- `typical_cost_high_usd` — High end cost per unit
- `supplier_type` — lumber_yard, electrical_supply, plumbing_supply, roofing_supply, big_box, specialty
- `hazmat_flag` — Boolean, true if hazardous material (chemicals, solvents)
- `notes` — Special notes

---

### Dataset 4: Customer Progress Examples
**File:** `datasets/customer_updates/customer_updates_v1.jsonl`
**Count:** 1,000 examples
**Format:** JSONL
**Generator:** `scripts/generators/generate_customer_updates.py`

**Structure (each record):**
```json
{
  "id": "uuid",
  "log_date": "2024-03-15",
  "technical_summary": "Framing of second floor complete. 8 workers. Rain delayed plastering 3 hours. Tomorrow: plumbing rough-in begins.",
  "project_stage": "framing",
  "completion_percent": 35,
  "tone": "professional",
  "customer_email_subject": "Project Update — March 15",
  "customer_email_body": "Dear Mr. Johnson, I am pleased to report excellent progress on your new home. ..."
}
```

**Pair generation strategy:**
- Generate a technical summary (foreman-style, from log data)
- Generate a professional client email from the summary (using templates with variation)
- Vary tone: formal, friendly, detailed, brief
- Cover all stages and progress milestones
- Include some with delays (communicated professionally)
- Include some with inspection results

---

### Dataset 5: Project Schedules
**File:** `datasets/schedules/project_schedules_v1.jsonl`
**Count:** 1,000 schedules
**Format:** JSONL
**Generator:** `scripts/generators/generate_schedules.py`

**Structure (each record):**
```json
{
  "schedule_id": "uuid",
  "project_type": "residential_single_family",
  "total_sqft": 2400,
  "project_start_date": "2024-01-15",
  "stages": [
    {
      "stage_id": "foundation",
      "planned_start": "2024-01-15",
      "planned_end": "2024-01-25",
      "actual_start": "2024-01-15",
      "actual_end": "2024-01-28",
      "delay_days": 3,
      "delay_reason": "weather",
      "completion_percent": 100
    }
  ],
  "critical_path_stages": ["foundation", "framing", "..."],
  "total_planned_days": 180,
  "total_actual_days": 192,
  "schedule_variance_days": 12,
  "weather_delay_days": 8,
  "inspection_delay_days": 3,
  "material_delay_days": 1
}
```

---

## Folder Structure (Sprint 2 Only)

```
Construction-Site-AI/
├── knowledge/                         ← Sprint 1 (frozen)
├── docs/                              ← Sprint 1 + Sprint 1.1
│
├── datasets/                          ← NEW Sprint 2
│   ├── README.md                      ← Dataset documentation
│   ├── daily_logs/
│   │   ├── daily_logs_v1.jsonl        ← 5,000 generated logs
│   │   └── daily_logs_v1_stats.json   ← Generation statistics
│   ├── safety_talks/
│   │   ├── safety_talks_v1.csv        ← ~200 OSHA-based talks
│   │   └── sources.md                 ← OSHA document citations
│   ├── materials/
│   │   └── materials_v1.csv           ← ~500 materials
│   ├── customer_updates/
│   │   └── customer_updates_v1.jsonl  ← 1,000 technical-to-email pairs
│   └── schedules/
│       └── project_schedules_v1.jsonl ← 1,000 project schedules
│
├── scripts/                           ← NEW Sprint 2
│   ├── README.md
│   └── generators/
│       ├── __init__.py
│       ├── config.py                  ← Generator configuration
│       ├── generate_daily_logs.py     ← Dataset 1 generator
│       ├── generate_safety_talks.py   ← Dataset 2 generator
│       ├── generate_materials.py      ← Dataset 3 generator
│       ├── generate_customer_updates.py ← Dataset 4 generator
│       └── generate_schedules.py      ← Dataset 5 generator
│
└── tests/                             ← NEW Sprint 2
    ├── README.md
    └── test_generators/
        ├── __init__.py
        ├── test_daily_logs.py          ← Validates generated log quality
        ├── test_materials.py           ← Validates material database
        └── test_schema_compliance.py   ← Validates all outputs against JSON Schema
```

---

## Acceptance Criteria

Sprint 2 is only complete when ALL of the following are true:

### Dataset Quality
- [ ] 5,000 daily logs generated with no validation errors (all pass `validation_rules.json`)
- [ ] No painting-before-drywall violations in any log
- [ ] No concrete-during-painting-stage violations in any log
- [ ] Rain frequency ≤ 25% per project
- [ ] Material usage matches stage in ≥ 95% of records
- [ ] Stage sequencing is valid in all 5,000 logs (no impossible backward jumps)
- [ ] At least 10 different worker counts per stage appear in dataset
- [ ] All 5 dataset files exist with correct format

### Code Quality
- [ ] All generators accept `--seed` for reproducibility
- [ ] All generators produce identical output given the same seed
- [ ] All generators write progress logs using Python `logging` module
- [ ] All generators have docstrings and type hints
- [ ] No hardcoded values — all configuration via `config.py` or `--args`
- [ ] Generators load rules from `knowledge/` files (not hardcoded rules)

### Testing
- [ ] `pytest tests/` passes 100%
- [ ] Schema compliance test validates every generated record against JSON Schema

### Documentation
- [ ] `datasets/README.md` explains each dataset: source, format, use case
- [ ] `scripts/README.md` explains how to run each generator
- [ ] Generation statistics logged and saved to `*_stats.json` files

---

## Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Stage sequencing logic is too complex for clean code | Medium | High | Use `dependency_graph.json` as state machine — never code rules manually |
| Generated data doesn't feel realistic | Medium | Medium | Verify with sample review of 50 random records before completion |
| Validation rules conflict with each other | Low | Medium | Run rules in priority order (Phase 1 blocking first) |
| Customer update generation produces repetitive text | High | Low | Use 20+ template variations; Sprint 4 will regenerate with real AI |

---

## Dependencies

**Must be complete before Sprint 2 starts:**
- [x] `knowledge/construction_rules.json` — Used by generator for sequencing
- [x] `knowledge/dependency_graph.json` — Used as state machine for stage sequencing
- [x] `knowledge/validation_rules.json` — Used to validate every generated record
- [x] `knowledge/construction_stages.json` — Used for worker counts and material selection
- [x] `knowledge/construction_daily_log_schema.json` — Target format for Dataset 1

**Python environment needed for Sprint 2:**
- Python 3.12
- `jsonschema` library (for schema validation)
- `faker` library (for realistic names, addresses)
- `pytest` (for tests)
- No Docker required for Sprint 2 — pure Python scripts

**Install command (Sprint 2 will include `requirements-dev.txt`):**
```bash
pip install jsonschema faker pytest
```

---

## Estimated Timeline

| Day | Task |
|-----|------|
| Day 1 | Set up `scripts/` and `datasets/` folder structure, `requirements-dev.txt`, `config.py` |
| Day 2 | Build Dataset 1 generator (`generate_daily_logs.py`) with stage state machine |
| Day 3 | Validate Dataset 1 (run validation rules), fix issues, generate all 5,000 logs |
| Day 4 | Build Datasets 2, 3, 4, 5 generators |
| Day 5 | Write tests, run full validation suite, write documentation, Sprint Review |
