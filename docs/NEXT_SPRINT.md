# Next Sprint: Sprint 12 — Inventory and Procurement

**Status:** READY TO BEGIN — Sprint 11 approved 2026-09-16 (see `docs/PROJECT_STATE.md`).
**Prerequisites:** Sprint 11 APPROVED and FROZEN — satisfied. PostgreSQL, Redis, and a running Celery worker (Sprint 9 requirements) still apply. Sprint 11's `ProjectSchedule`/`ScheduleTask` tables are a direct input to Deliverable 4 (lead-time warnings) below.

---

## Sprint 12 Goal

Per `docs/ROADMAP.md`'s Phase 4 plan: material consumption tracking from daily logs, auto-generated purchase orders, lead-time warnings ("order countertops now or miss your closing date"), and supplier integration preparation.

**This is a different shape of sprint than 11, but for a related reason.** Sprint 11 needed new tables because no schedule existed anywhere in the production database. Sprint 12 is the same situation for materials: `log_materials_used`, `log_materials_delivered`, and `log_materials_required` (all Sprint 6, frozen) are per-log line items with **no persistent identity across logs** — there is no `inventory_items`, `suppliers`, or `purchase_orders` table anywhere. Two different daily logs both mentioning "Cement bags" are three unrelated rows today; nothing connects them into "how much cement does this project have on hand," because nothing tracks running quantity across time. Sprint 12's real new capability is giving materials that persistent identity, the same way Sprint 11 gave stages a persistent per-project schedule.

What already exists and should NOT be rebuilt:
- `generation/prompts/material_reminder.md` + `MaterialReminderService` (Sprint 5) — already produces a **single-log** CRITICAL/HIGH/MEDIUM/LOW procurement reminder from one day's `materials_used`/`materials_required`/`shortage_flags`. This is narrative, per-log, LLM-generated text. Sprint 12 does NOT replace it or duplicate its job — it adds the cross-log, deterministic layer underneath: real running quantity, real reorder thresholds, real lead-time math. Whether the existing generation service should read the new inventory tables to ground its "Source TBD" gaps is a real question to decide during implementation (see Deliverable 5), not assumed.
- `LogMaterialUsed` / `LogMaterialDelivered` / `LogMaterialRequired` (`database/models/log_items.py`) — the per-log source data this sprint aggregates *from*. Not modified; Sprint 12 reads them, it doesn't restructure them. Note `LogMaterialDelivered.purchase_order_number` already exists as a free-text string column — unused by anything today, evidently anticipating this sprint the same way `LogWorkItem.linked_schedule_task_id` anticipated Sprint 11.
- `datasets/exports/materials_v1.csv` (Sprint 2) + `dataset_generation_framework/generators/material_generator.py` — a **small (5-row) illustrative sample**, not a large ground-truth dataset the way `dependency_graph.json` was for Sprint 11. Useful only as a field-shape reference (`reorder_point`, `lead_time_days`, `qty_on_hand`, `supplier`, `primary_stage_used`/`applicable_stages` — the last two are literally `knowledge/dependency_graph.json` stage ids, already anticipating a materials-to-schedule join) — not something to seed real inventory rows from. Do not treat its 5 rows as real starting inventory for any project.
- `Project.contract_value_usd` / `project_start_date` / `planned_completion_date` (Sprint 6) — already exist; a purchase order's cost rolls up against the first, and Deliverable 4's "missed your closing date" framing needs the second two (already read by Sprint 11's schedule creation).
- Sprint 11's `ScheduleTask` (`stage_id`, `planned_start_date`, `planned_end_date`) — the input Deliverable 4 needs to compute "material X, needed for stage Y, which starts in N days, has a Z-day lead time — order by [date] or the stage will be delayed." No code changes needed to `ScheduleTask` itself; this sprint only reads it, the same read-only relationship Sprint 11's own delay-impact computation has with `dependency_graph.json`.

---

## Deliverables

### 1. `InventoryItem` and `PurchaseOrder` Tables (New Migration)

The real new capability this sprint needs, following the same normalization pattern Sprint 11 used (and Sprint 6 established): a parent identity table plus child rows for the repeating structure.

- `inventory_items` — one row per distinct material **per project** (not global across companies — a "Cement bags" row on Project A and Project B are different inventory items with independent quantities, matching how `LogMaterialUsed` is already scoped per log per project). Fields: `material_name`, `category`, `unit`, `quantity_on_hand`, `reorder_point`, `typical_lead_time_days`, `preferred_supplier` (plain string, matching `LogMaterialUsed.supplier`'s existing shape — see Deliverable 6 on why a full `suppliers` table is likely out of scope), `last_counted_at`.
- `purchase_orders` — one row per order: `inventory_item_id` (FK), `quantity_ordered`, `unit_cost_usd`, `supplier`, `status` (`draft | submitted | delivered | cancelled` — decide the exact set during implementation; must at minimum distinguish "system suggested this, nobody acted on it yet" from "someone actually placed it"), `ordered_at`, `expected_delivery_date`, `actual_delivery_date`, `auto_generated` (boolean — did Deliverable 2 create this, or did a human).

New Alembic migration `006_inventory.py`. `LogMaterialDelivered.purchase_order_number` (currently unconstrained free text) becomes the natural place to decide, during implementation, whether to backfill/link it to a real `purchase_orders.id` — same soft-vs-hard-FK decision Sprint 11 made for `LogWorkItem.linked_schedule_task_id`, and likely the same answer (soft, documented, not enforced) for the same reason: existing `LogMaterialDelivered` rows predate this table and a backfill has no reliable source to match against.

### 2. Material Consumption Tracking (Reconciling `inventory_items` from Daily Logs)

- On daily log approval (extending the same hook point Sprint 11, Deliverable 4 added to `POST /daily-logs/{id}/approve` — this sprint's reconciliation slots in next to the schedule-actual-dates update, not a separate new hook), walk the approved log's `materials_used` and `materials_delivered` child rows: decrement `inventory_items.quantity_on_hand` for each `materials_used` entry (creating the `inventory_item` row on first mention if it doesn't exist yet for this project — there is no separate "register a material" step), increment it for each `materials_delivered` entry.
- Deliberately best-effort and isolated, matching Sprint 11's own fix for this exact failure mode (see `docs/DECISIONS.md`'s Sprint 11 Known Bugs #3): a reconciliation failure must never undo the log approval itself. Commit the approval first, then attempt reconciliation in its own transaction.
- `materials_required` entries do NOT decrement/increment anything — they're a forward-looking request, not a consumption event. They feed Deliverable 4 instead.

### 3. Auto-Generated Purchase Orders

- When `quantity_on_hand` drops to or below `reorder_point` for an `inventory_item` (checked as part of the Deliverable 2 reconciliation step, not a separate poller — Sprint 11 has no Celery Beat and this sprint doesn't need one either, per the "no scheduler exists" finding `docs/RESUME_AUDIT_2026-09-15.md` confirmed), create a `purchase_orders` row with `status="draft"`, `auto_generated=True`, `quantity_ordered` defaulted to some sensible restock amount (decide the formula during implementation — e.g. reorder_point × 2, or driven by `typical_lead_time_days` × average daily consumption rate if that's computable from log history; document whichever is chosen as an ADR, the same way Sprint 11 documented its CPM/variance formulas).
- A draft, auto-generated PO is a **suggestion**, not an order actually placed — no real supplier integration exists (Deliverable 6 explicitly scopes that out). A human reviews and moves it to `submitted` via a new endpoint (Deliverable 4's API surface).
- `GET /projects/{id}/inventory` — list current inventory items + quantities + any open (non-`cancelled`, non-`delivered`) purchase orders per item, tenant-scoped like every other project sub-resource.
- `POST /projects/{id}/inventory/{item_id}/purchase-orders` — human-initiated PO creation (the manual counterpart to the auto-generated path), and a status-transition endpoint (`PATCH .../purchase-orders/{po_id}` or similar — decide the exact shape during implementation, matching the existing `PATCH /users/{id}/role`-style single-field-transition pattern already used elsewhere in this API).

### 4. Lead-Time Warnings

- The deliverable the roadmap's own example names directly: "order countertops now or miss your closing date." For each `inventory_item` with `typical_lead_time_days` set, cross-reference against Sprint 11's `ScheduleTask` rows via `applicable_stages`-style matching (the materials CSV sample's field shape — `primary_stage_used`, matching a `dependency_graph.json`/`ScheduleTask.stage_id` value — is the reference for how this join should work; decide during implementation whether `inventory_items` needs its own `applicable_stage_id` column to make this join direct, rather than inferring it from material name text each time).
- Pure date arithmetic, no AI/LLM call — matching Sprint 11's ADR-048 posture exactly ("no AI where deterministic logic suffices"). A warning fires when `schedule_task.planned_start_date - typical_lead_time_days` is on or before "today" and no `submitted`/`delivered` purchase order covers a sufficient quantity of that material for that stage. Message shape: deterministic string template, not generated prose (again matching ADR-048 — this is `f"Order {material} now — {lead_time} day lead time, {stage} starts in {days_until} days"` arithmetic, not a Groq call).
- Surface warnings on `GET /projects/{id}/inventory`'s response (a `lead_time_warnings` field, computed at read time like Sprint 11's `variance`/`delay_adjusted_completion_date` fields — never persisted, always reflects current schedule + inventory state) and, if it fits naturally, as a small panel on the frontend Dashboard or Schedule page (decide placement during implementation — a natural fit given `SchedulePanel.tsx` already exists and displays per-stage data).

### 5. Frontend — Inventory Panel

- A new `InventoryPanel.tsx` (or extend `SchedulePanel.tsx` — decide during implementation which reads better; Sprint 11's `SchedulePanel` already has the per-stage Gantt context lead-time warnings need) showing current inventory levels, reorder-point status (a color-coded badge, matching `MaterialReminderContent.tsx`'s existing CRITICAL/HIGH/MEDIUM/LOW pattern rather than inventing a new visual language), open purchase orders, and lead-time warnings.
- A "Create purchase order" action for the roles that can already generate/manage project data (reuse `Permission.PROJECT_MANAGE` or a new narrower permission — decide during implementation whether inventory management needs its own permission or fits the existing project-management one; document the choice).
- Whether `MaterialReminderContent.tsx`'s single-log reminder should link to or reference the new cross-log inventory view is a real UX question, not assumed — decide during implementation.

### 6. Supplier Integration Preparation

- The roadmap explicitly scopes this as **preparation**, not a real integration — there is no case in this project's history (ADR-005, ADR-007, Sprint 11's own "no paid APIs" constraint) for reaching out to a real supplier API this sprint. `preferred_supplier` stays a plain string on `inventory_items` (Deliverable 1), matching `LogMaterialUsed.supplier`'s existing shape, not a normalized `suppliers` table with contact details, API credentials, etc. — that normalization is only worth doing once a second concrete need for it exists (the same "denormalization is a documented, conscious choice" reasoning `database/models/project.py`'s `client_name` docstring already uses for an analogous case).
- If a full `suppliers` table turns out to be needed once Deliverable 3's PO-creation flow is actually built (e.g. because multiple inventory items share exactly one supplier and duplicating the string everywhere is clearly wrong), that is a legitimate mid-implementation discovery — document it as an ADR if it happens, but don't build it speculatively up front.

### 7. Tests

- `tests/test_db_repositories.py` (extended) or a new `tests/test_inventory_repository.py` — inventory CRUD, tenant scoping, the consumption-reconciliation logic (decrement/increment math), matching Sprint 11's `tests/test_api_schedule.py` structure.
- `tests/test_api_inventory.py` — `GET/POST /projects/{id}/inventory`, tenant isolation (the same two-company pattern every Sprint 9–11 test file uses), the approval-hook reconciliation (mirroring `tests/test_api_schedule.py`'s `TestApprovalPopulatesActualDates` pattern exactly, since this sprint extends the same hook point).
- `tests/test_lead_time_warnings.py` — pure-function tests against small hand-built fixtures (inventory item + schedule task + known lead time → expected warning or none), matching `tests/test_critical_path.py`'s "small, hand-verifiable" approach rather than the full 23-node real graph.
- Frontend: `InventoryPanel.test.tsx` (or the extended `SchedulePanel.test.tsx`), matching Sprint 9/10/11's Vitest + Testing Library pattern.
- **Given Sprints 9, 10, and 11 each found real, live-verification-only bugs** (duplicate documents, PDF font corruption, missing RBAC gating, an attribute-name mismatch, a lag-undercounted total, a transaction-isolation bug, a lossy dict reconstruction, a status masking a failure) **that no mock-based test caught** — continue verifying every deliverable live (real backend, real database, real browser for the frontend panel) before considering it done, not just green tests. Specifically: after Deliverable 2 ships, approve a real log with real `materials_used`/`materials_delivered` data and confirm `quantity_on_hand` actually moved in the real database — the exact category of check that caught Sprint 11's transaction-isolation bug.

---

## Constraints

- **No paid APIs, no paid SaaS, no real supplier integration.** Matches ADR-005/ADR-007's posture and Sprint 12's own Deliverable 6 scoping.
- **Sprint 1–11 FROZEN.** Extend `app/`/`database/`/`frontend/`, do not rewrite Sprint 5's `MaterialReminderService`, Sprint 6's `LogMaterial*` tables, or Sprint 11's schedule code unless fixing a verified bug (see `docs/CONTRIBUTING.md` §5).
- **Maintain backward compatibility.** Every existing endpoint's contract continues to work unchanged. `LogMaterialDelivered.purchase_order_number` stays a nullable free-text column regardless of whether Deliverable 1 links it — no existing row needs to change.
- **Continue the "explain, implement, test, verify" per-subsystem discipline**, live verification over mock-based tests — the discipline that has caught real bugs in every sprint from 9 through 11.
- **No AI/LLM calls for inventory math, reorder logic, or lead-time warnings** (Deliverables 2–4) — this is deterministic arithmetic over structured data, matching Sprint 11's ADR-048 posture exactly. The existing `MaterialReminderService` (Sprint 5) is the one place in this sprint's scope that legitimately still uses Groq, and it is explicitly not being touched or duplicated.

---

## Explicit Out of Scope for Sprint 12

- Real supplier API integration (purchase order transmission, live pricing, order tracking) — Deliverable 6 is explicitly preparation only
- A normalized `suppliers` table with contact/credential data — `preferred_supplier` stays a plain string unless a concrete mid-implementation need surfaces (see Deliverable 6)
- Global (cross-project, cross-company) inventory pooling — `inventory_items` scopes to one project, matching every other tenant-scoped resource in this codebase
- Automatic PO submission (an auto-generated PO is always `status="draft"` until a human acts on it) — no code path in this sprint transmits an order anywhere
- Barcode/QR scanning, physical inventory-count hardware integration
- Sprint 13's Analytics Dashboard, Sprint 14's Cost Intelligence — later sprints per `docs/ROADMAP.md`'s Phase 4 plan
- Production Docker deployment, multi-company admin UI — still open per every prior sprint spec's own out-of-scope list, unless explicitly pulled forward
