# Next Sprint: Sprint 17 — Reference-Cost Project Estimator

**Status:** READY TO BEGIN — Sprint 16 approved 2026-09-17 (see `docs/PROJECT_STATE.md`).
**Prerequisites:** Sprint 16 APPROVED and FROZEN — satisfied. PostgreSQL, Redis, and a running Celery worker (Sprint 9 requirements) still apply.

---

## Sprint 17 Goal

Per `docs/ROADMAP.md`'s Phase 5 plan, the two remaining items are Defect Detection and Bid Estimation. Both were investigated in detail before writing this spec, and **both are genuinely blocked as roadmapped** — not a scope to attempt and hope for the best, per this project's standing discipline of investigating before committing to a sprint's premise:

- **Defect Detection is blocked twice over.** There is no photo/image upload infrastructure anywhere in this codebase — `attachments` exists only as an always-null passthrough column (`database/models/daily_log.py`) with no endpoint that ever writes to it; the only file-upload endpoint (`app/api/v1/audio.py`) is hardcoded to `{.wav, .mp3, .m4a, .flac, .ogg, .webm, .mp4}`; `data/uploads/` on disk contains zero images; the frontend has microphone capture (`RecordPage.tsx`) but no camera/photo UI anywhere. And even with upload infrastructure built, there is no verified path to a vision-capable model: the pinned `groq==1.5.0` SDK's type system includes an `image_url` content-part shape, but the currently configured model (`openai/gpt-oss-120b`) has no confirmed vision capability, and nothing in `extraction/` has ever exercised it. This is two new infrastructure categories stacked on each other, not a contained gap.
- **Bid Estimation is blocked on data, not code.** The roadmap's own framing — "historical project data → bid estimate for new project" — requires historical projects. There is exactly **one project in the entire database** (`aaaaaaaa-0006-4000-8000-000000000006`, 3 approved daily logs), confirmed by direct query. Generating more synthetic seed projects to feed this would be circular: a seed generator's own invented numbers "predicting" a bid, verified only against that same generator's assumptions — not a real feature, and not live-verifiable against anything real.

**Sprint 16 independently reached the identical conclusion about both items when scoping itself** (see `docs/DECISIONS.md`'s Sprint 16 section) — this sprint re-confirmed rather than re-litigated that finding, and the user was asked directly how to proceed given both roadmapped items are blocked. The direction chosen: **build the part of "bid estimation" that's honestly buildable today** — a deterministic reference-cost range estimator, explicitly *not* claiming to use historical project data, built instead on real reference data this codebase already has:

- **`knowledge/construction_ontology.json`'s 16 materials each carry a real `cost_range_per_unit_usd`** (e.g. ready-mix concrete $120–180/cu-yd, rebar #4 $0.40–0.70/linear-ft), plus `used_in_stages`/`used_by_trades` associations — confirmed by direct inspection, not assumed. This is real reference data, already used elsewhere in the codebase (extraction/generation prompts reference the ontology's trade/material vocabulary), just never used for cost estimation.
- **`knowledge/dependency_graph.json`'s 23 stage nodes carry real `typical_duration_days`** and critical-path/parallel-group structure — the same data Sprint 11's scheduling module already seeds every new `ProjectSchedule`/`ScheduleTask` from. A project's real, already-persisted `ScheduleTask` rows (not a fresh ontology lookup) tell us exactly which stages apply to that specific project, in what order, for how long — reusable as-is, not rebuilt.
- **`Project.project_size_sqft` and `Project.contract_value_usd` are real, already-populated columns** (`database/models/project.py`) — confirmed by inspection. `project_size_sqft` gives something to scale a materials estimate against; `contract_value_usd`, where set, gives a real number to sanity-check the estimate against on the one real seeded project — a genuine live-verification anchor, not a synthetic one.
- **What's missing, and has to be built new, not looked up:** there is no quantity-takeoff data anywhere (no "cubic yards of concrete per square foot of foundation," no labor-hours-per-unit figures). A real estimator needs a small, new, explicitly-labeled-as-approximate quantity model — e.g. a per-stage "typical quantity per 1,000 sqft" table for the materials most tied to that stage — checked into `knowledge/` alongside the existing ontology, with the same "typical_" naming convention the dependency graph already uses for its duration estimates, and every output range explicitly labeled as a reference estimate, never as a quote or a historical-data-driven prediction.

**What this means for scope:** no new database tables are needed (the estimate is a computed read, following the established "read-time-only projection" pattern from Sprint 13 onward — variance, EVM, safety warnings are all precedent for "compute fresh on every GET, never persist"). The real work is (a) building the missing quantity-per-stage reference data as a new knowledge file, explicitly labeled as typical ranges, (b) a new deterministic computation service combining that data with a project's real schedule stages and size, (c) a new endpoint exposing it, and (d) a UI surface for it — all in the same "no AI where deterministic logic suffices" posture as Sprint 11's schedule variance and Sprint 14's budget/EVM math (ADR-005/007/048).

What already exists and should NOT be rebuilt:
- `knowledge/construction_ontology.json`'s material cost ranges and `knowledge/dependency_graph.json`'s stage durations — real, used as-is, not regenerated.
- `ScheduleTask` rows (Sprint 11) — a project's real, already-computed stage list/sequence/duration. The estimator reads these, it does not recompute stage applicability from scratch.
- `Project.project_size_sqft`/`contract_value_usd` — real columns, used as inputs, not new schema.
- The "read-time-only projection" pattern (Sprint 13's variance fields, Sprint 14's EVM, Sprint 15's safety warnings) — this sprint's estimate follows the identical shape: computed fresh on every GET, never persisted, degrading gracefully when an input (e.g. `project_size_sqft`) is missing.

---

## Deliverables

### 1. Build a Quantity-Per-Stage Reference Table

- New knowledge file, e.g. `knowledge/cost_estimation_reference.json`, keyed by `stage_id` (matching `dependency_graph.json`'s existing stage ids exactly, so it composes with real `ScheduleTask.stage_id` values already in the database) — for each stage, a small list of `{material_id (matching ontology ids), typical_quantity_per_1000_sqft, unit}` entries for the materials most characteristic of that stage. Scope this to the stages that dominate residential cost (foundation, framing, roofing, drywall, concrete flatwork, electrical rough-in, plumbing rough-in — a subset, not all 23 stages need quantity data if a stage has no material-driven cost worth estimating, e.g. inspections).
- Every figure must be labeled in the file's own `_metadata` block as a **typical/approximate reference range**, not a precise takeoff — matching the existing ontology's own `cost_range_per_unit_usd` framing (a range, not a point estimate) and this project's established honesty about estimate precision (Sprint 14's EVM explicitly documents its own linear-accrual simplification; this should too).
- Do not invent labor-hour figures if no defensible reference number is readily available — a materials-only estimate, honestly scoped, is preferable to a fabricated labor number presented with false confidence. Decide and document this scope boundary explicitly (likely an ADR: "materials-only, no labor hours, because no defensible reference source exists for labor rates in this dataset").

### 2. `app/services/cost_estimation_service.py` — Deterministic Estimate Computation

- A new service, same shape as `app/services/cost_service.py` (Sprint 14) and `app/services/safety_trend_service.py` (Sprint 15): pure functions, no AI/LLM call, no persistence.
- Given a project's real `ScheduleTask` rows (stage ids, already computed by Sprint 11) and `Project.project_size_sqft`, compute a low/high cost range per stage (quantity-per-1000-sqft × sqft/1000 × the ontology's own `cost_range_per_unit_usd`) and a project-total low/high range.
- Handle missing `project_size_sqft` explicitly (return a clear "not enough data" result for the whole computation, not a silent zero or a crash) — the same missing-input-degrades-gracefully posture as Sprint 14's EVM fields.
- Where `Project.contract_value_usd` is also set, include a simple comparison note (e.g. "contract value falls within/above/below the reference estimate range") — this is the closest this sprint gets to "bid estimation," and it must be framed as a sanity-check against a reference range, never as validating or second-guessing a real signed contract number.

### 3. `GET /projects/{id}/cost-estimate` Endpoint

- New endpoint, gated the same way Sprint 14's cost/budget data and Sprint 15's OSHA export were — staff-only, reusing `STAFF_ONLY_ANALYTICS_ROLES`/the appropriate `Permission` (confirm which by checking how Sprint 14's `budget_variance`/`earned_value` fields on `GET /projects/{id}/analytics` are gated, and decide whether this belongs as a new field on that same endpoint or a standalone one — investigate before assuming; Sprint 13–15 all extended the analytics endpoint rather than adding new ones, which may be the more consistent choice here too).
- Live-verify against the real seeded project: confirm the computed range is plausible given its real `project_size_sqft`, and if `contract_value_usd` is set, confirm the comparison note is correct.

### 4. Frontend: Surface the Estimate

- Extend `AnalyticsPanel.tsx` (if Deliverable 3 folds into the analytics endpoint) with a "Reference cost estimate" section, staff-only, following the exact pattern of Sprint 14's "Cost and budget" and Sprint 15's "Safety status" sections — a per-stage breakdown and a total range, clearly labeled as a reference estimate rather than a quote.
- Live-verify with a real Playwright browser session, including confirming the `client` role still sees none of it (matching every prior staff-only section's precedent).

---

## Constraints

- **No paid APIs, no paid SaaS, no new AI/LLM calls.** This is explicitly a "no AI where deterministic logic suffices" sprint (ADR-005/007/048's posture) — a pure computation over reference data and a project's real schedule/size, not a model call.
- **Sprint 1–16 FROZEN.** Extend `knowledge/`/`app/`/`frontend/`; do not modify `dependency_graph.json`'s or `construction_ontology.json`'s existing content — add a new file alongside them.
- **No new database tables** — this follows the established read-time-only projection pattern; nothing here needs to be queried by anything other than the one new endpoint, so persistence would be premature.
- **Never call this a "bid" or a "quote."** Every user-facing label (API field names, UI copy, ADR wording) must make clear this is a reference-range estimate from typical-quantity data, not a historical-data-driven prediction and not a substitute for a real contractor bid — this is the honesty boundary the whole sprint exists to respect, given the roadmap's original "historical project data" framing is not actually being delivered.
- **Continue the "explain, implement, test, verify" per-subsystem discipline**, live verification over mock-based tests — verify the computation against the one real seeded project's real `project_size_sqft`/`contract_value_usd`/`ScheduleTask` rows, not only synthetic unit-test fixtures.

---

## Explicit Out of Scope for Sprint 17

- Labor-hour estimation — no defensible reference data source exists in this codebase for labor rates; materials-only, documented as a deliberate scope boundary (see Deliverable 1).
- Any actual computer-vision defect detection, or any photo/image upload infrastructure — still blocked exactly as this spec's investigation found; not attempted here.
- Any true historical-data-driven estimation — remains blocked by the single-project database; revisit only once real multi-project historical data exists.
- Editing or regenerating `dependency_graph.json`/`construction_ontology.json`'s existing content — this sprint adds a new, separate reference file rather than modifying frozen knowledge-base data.
- Per-region cost variance, inflation adjustment, or any external pricing API/feed — the existing ontology's static USD ranges are used as-is, same as every other sprint that has consumed them.
