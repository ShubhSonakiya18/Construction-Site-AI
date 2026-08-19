# Next Sprint: Sprint 11 — Scheduling Module

**Status:** READY TO BEGIN — Sprint 10 approved 2026-08-19 (see `docs/PROJECT_STATE.md`).
**Prerequisites:** Sprint 10 APPROVED and FROZEN — satisfied. PostgreSQL, Redis, and a running Celery worker (Sprint 9 requirements) still apply.

---

## Sprint 11 Goal

Per `docs/ROADMAP.md`'s Phase 4 plan: Gantt chart generation, schedule variance detection, critical path tracking, and delay impact prediction — all derived from data this project already has, some of it built specifically anticipating this sprint.

**This is a different shape of sprint than 9 or 10.** Sprints 9–10 added surface area over existing data with no new tables. Sprint 11 needs a real schema addition: there is currently **no `Schedule`/`Task`/`Milestone` table anywhere in the production database.** Sprint 2's `dataset_generation_framework/generators/schedule_generator.py` produces a `ConstructionProjectSchedule`-shaped synthetic dataset (`project_schedules_v1.jsonl`) for training/test data only — it is not persisted, not queried by any repository, and its `project_id` is a synthetic seeded UUID, not a real foreign key. Its schema is a reasonable reference for field naming, not something to import directly.

What already exists and should NOT be rebuilt:
- `knowledge/dependency_graph.json` — 23 nodes, 33 edges, **already contains a precomputed critical path** (`critical_path.path_nodes_in_order`, `typical_total_days: 97`, `typical_duration_breakdown`), parallel-execution groups, and a topological sort. This is the authoritative source for "what stage typically takes how long and in what order" — read it, don't re-derive it.
- `LogWorkItem.linked_schedule_task_id` (`database/models/log_items.py:164-168`) — already has the doc comment "Reference to project schedule task. Used by Sprint 11 Scheduling module." A nullable string column, currently unused by anything. This is the intended link between an actual logged work item and a schedule task row this sprint creates.
- `LogDelay.schedule_impact` and `days_lost_to_schedule` (`database/models/log_items.py:571`) — the class docstring literally says "Which delay types most impact critical path? (Sprint 11 scheduling)". Already queried in aggregate by Sprint 10's `get_delay_frequency_scoped()`; this sprint is where `schedule_impact`/`days_lost_to_schedule` finally get used for something beyond storage.
- `Project.project_start_date` / `planned_completion_date` / `actual_completion_date` — already exist, already the two dates a Gantt chart's overall span needs.

---

## Deliverables

### 1. `ProjectSchedule` / `ScheduleTask` Tables (New Migration)

The real new capability this sprint needs. Two tables, following this project's existing normalization pattern (one parent row, child rows for the repeating structure — the same shape `DailyLog` + its 11 child tables already use):

- `project_schedules` — one row per project (or per schedule revision, if replanning support is wanted — decide during implementation whether a project can have multiple schedule revisions or exactly one active schedule; the spec here assumes one active schedule per project unless a revision need becomes concrete).
- `schedule_tasks` — one row per stage/task in that schedule: `stage_id` (matching `dependency_graph.json` node ids), `planned_start_date`, `planned_end_date`, `planned_duration_days`, `actual_start_date`, `actual_end_date`, `is_on_critical_path` (seeded from `dependency_graph.json`, not recomputed per-project unless Deliverable 3 needs a per-project recomputation), `sequence_order`.

New Alembic migration `005_scheduling.py`. `LogWorkItem.linked_schedule_task_id` becomes a real (nullable) FK to `schedule_tasks.id` — currently just a string column with no constraint; decide during implementation whether to add the FK constraint now (tightens the intended link) or leave it soft (avoids a backfill problem for existing rows that never set it). Document the choice as an ADR either way.

### 2. Gantt Chart Generation

- A new repository method building a Gantt-ready structure per project: for each `schedule_tasks` row, planned start/end, actual start/end (once logged), and whether it's on the critical path — directly consumable by a Gantt chart component.
- `GET /projects/{id}/schedule` — returns the schedule + all tasks, tenant-scoped like every other project sub-resource.
- Frontend: a Gantt chart component on the Dashboard or a new `/projects/{id}/schedule` page — evaluate a lightweight Gantt library (e.g. `frappe-gantt`, `gantt-task-react`) vs. hand-rolling one on top of `recharts`/SVG (Sprint 10 already proved `recharts` works well in this codebase for a bar/line chart, but a real Gantt with dependency arrows is a different shape of chart than either of Sprint 10's two). Decide during implementation, document as an ADR — matching how Sprint 10 decided reportlab vs. weasyprint and recharts vs. chart.js as explicit, documented choices rather than defaults.

### 3. Schedule Variance Detection

- Compare `schedule_tasks.actual_start_date`/`actual_end_date` (populated as logs come in — see Deliverable 4) against `planned_start_date`/`planned_end_date`. A task whose actual progress is behind its planned schedule as of "today" (relative to the log dates seen so far) is in variance.
- The example in `docs/ROADMAP.md` — "you're 5 days behind on framing" — implies a specific, human-readable variance message per task, not just a raw day-count delta. Reuse this project's existing generation pattern (a new `ServiceType`? or a simpler deterministic string template, since this is arithmetic on dates, not something that benefits from an LLM call) — decide during implementation whether this needs `AIServiceManager` at all or is pure computation; lean toward pure computation unless a real need for natural-language variance narrative emerges, consistent with this project's "don't add AI where deterministic logic suffices" posture (no prior sprint has used an LLM for something this arithmetic).

### 4. Populating Actual Dates from Daily Logs

- `DailyLog.current_stage` + `log_date` is the real signal for "when did this stage actually start/progress." A new step (either in `run_pipeline()`'s post-persistence flow, Sprint 7, or a separate reconciliation job) that, when a `DailyLog` is approved, updates the matching `schedule_tasks` row's `actual_start_date` (first log date mentioning that stage) and `actual_end_date` (once `stage_completion_percent` reaches 100 or the stage is no longer in `active_stages` on a later approved log).
- This is the piece that makes Deliverable 3 (variance detection) meaningful — without it, "actual" dates never populate and every task shows as unstarted regardless of real progress.
- Decide during implementation: does this run synchronously on log approval (in the `/approve` endpoint, extending `DailyLogRepository.approve()`'s frozen state machine — check whether this counts as a "verified bug fix" exception to the freeze discipline, or whether it needs to be a new, additive post-approval hook instead) or as a Celery task (Sprint 9's task queue already exists for exactly this kind of "do more work after an approval" pattern). Document the choice.

### 5. Critical Path Tracking (Per-Project)

- `dependency_graph.json`'s critical path is generic (the "typical" 97-day critical path for any residential project). A per-project critical path reflecting THIS project's actual planned durations (which may differ from `typical_duration_days`) is a real computation — standard critical-path-method (CPM) forward/backward pass over the `schedule_tasks` graph, using `dependency_graph.json`'s edges for dependency structure.
- Scope narrowly: recompute the critical path once at schedule creation time (Deliverable 1) from planned dates; recomputing it continuously as actual dates diverge from plan (a "live" critical path) is a larger feature — decide whether that's in scope for this sprint or deferred, and document the decision.

### 6. Delay Impact Prediction

- The narrowest, most directly-supported-by-existing-data deliverable: for a delay recorded with `schedule_impact = "critical_path_impacted"` and `days_lost_to_schedule` set, propagate that day count forward through the dependent tasks in `schedule_tasks` (using the same dependency edges Deliverable 5 uses) to predict the new completion date.
- This is prediction only in the sense of "if this delay's impact holds, here's the new projected end date" — not a machine-learning prediction. Consistent with this project's existing posture (ADR-005, ADR-007, and every generation service): no ML model is warranted here, this is graph arithmetic over already-structured data.

### 7. Tests

- `tests/test_db_repositories.py` (extended) or a new `tests/test_schedule_repository.py` — schedule/task CRUD, tenant scoping.
- `tests/test_api_schedule.py` — `GET /projects/{id}/schedule`, tenant isolation (same two-company pattern every Sprint 10 test file used).
- `tests/test_schedule_variance.py` — variance computation correctness against known planned/actual date fixtures.
- `tests/test_critical_path.py` — CPM forward/backward pass correctness against a small, hand-verifiable dependency graph (not the full 23-node real one, for a fast, obviously-correct test fixture).
- Frontend: Gantt chart component tests (Vitest + Testing Library, per the Sprint 9/10 pattern), and a `roles.ts`-style check if the schedule view needs any new role gating (likely reuses `PROJECT_READ`, already granted to every role including `client` — verify during implementation rather than assuming).
- **Given Sprint 9 and 10 each found real, live-verification-only bugs (duplicate documents, PDF font corruption, missing RBAC gating) that no mock-based test caught** — continue verifying every deliverable live (real browser, real backend, real Groq/Redis/Celery where relevant) before considering it done, not just green tests.

---

## Constraints

- **No paid APIs, no paid SaaS.** Any Gantt charting library must be free/open-source, matching ADR-005/ADR-007's posture (same bar Sprint 10 applied to `reportlab` and `recharts`).
- **Sprint 1–10 FROZEN.** Extend `app/`/`database/`/`frontend/`, do not rewrite Sprint 7–10's services/routers/schemas/pages unless fixing a verified bug (see `docs/CONTRIBUTING.md` §5).
- **Maintain backward compatibility.** Every existing endpoint's contract continues to work unchanged. The new `schedule_tasks.id` FK on `LogWorkItem.linked_schedule_task_id` (Deliverable 1) is additive — existing rows with no value there stay valid regardless of whether the FK constraint is added strict or left soft.
- **Continue the "explain, implement, test, verify" per-subsystem discipline**, and continue live verification, not just mock-based tests — this is the discipline that caught 3 real bugs in Sprint 9 and 3 more in Sprint 10.

---

## Explicit Out of Scope for Sprint 11

- Multiple schedule revisions / replanning history per project (Deliverable 1 assumes one active schedule unless a concrete need surfaces)
- A "live," continuously-recomputed critical path as actual progress diverges from plan (Deliverable 5 scopes to compute-once-at-creation unless decided otherwise during implementation)
- Machine-learning-based delay prediction (Deliverable 6 is graph arithmetic, not ML — consistent with every prior sprint's AI-only-where-warranted posture)
- Sprint 12's Inventory and Procurement, Sprint 13's Analytics Dashboard (Sprint 10 already delivered a basic version — completion trend + delay frequency — Sprint 13 per `docs/ROADMAP.md` would extend it further), Sprint 14's Cost Intelligence — all explicitly later sprints per `docs/ROADMAP.md`'s Phase 4 plan
- Production Docker deployment, multi-company admin UI, API keys for external clients — still Sprint 10+/later per every prior sprint spec's own out-of-scope list, unless explicitly pulled forward
