# Next Sprint: Sprint 13 — Analytics Dashboard

**Status:** READY TO BEGIN — Sprint 12 approved 2026-09-16 (see `docs/PROJECT_STATE.md`).
**Prerequisites:** Sprint 12 APPROVED and FROZEN — satisfied. PostgreSQL, Redis, and a running Celery worker (Sprint 9 requirements) still apply. No new infrastructure needed — see Deliverable count below.

---

## Sprint 13 Goal

Per `docs/ROADMAP.md`'s Phase 4 plan: project completion trends, delay pattern analysis by trade, safety incident trends, productivity by stage and trade, and a client-facing progress portal.

**This is a lighter sprint than 11 or 12 — no new tables.** Every raw data point these five deliverables need already exists: `LogTradeOnSite.trade`/`hours_worked`, `LogWorkItem.task_completion_percent`, `LogSafetyIncident.incident_type`/`osha_recordable`, `LogDelay.delay_type` (already aggregated once, by Sprint 10), and `DailyLog.overall_project_completion_percent` (also already aggregated once, by Sprint 10). This sprint is aggregation and cross-referencing — new read-only queries and, in one case (Deliverable 5), a permission-boundary decision — not new schema, matching Sprint 10's own shape ("Nothing here required new AI generation logic... this sprint is surface area... and one new aggregation endpoint").

What already exists and should NOT be rebuilt:
- `GET /projects/{id}/analytics` (Sprint 10) — `DailyLogRepository.get_completion_trend_scoped()` (completion % over time) and `get_delay_frequency_scoped()` (delay type × occurrence count × hours lost), both approved-logs-only, both per-project. `AnalyticsPanel.tsx` on the Dashboard already renders both with `recharts`. Sprint 13 does NOT replace this endpoint or its two existing series — Deliverable 1 (completion trends) is explicitly "the same thing, done well," not a new capability; verify during implementation whether extending the existing response is more honest than adding a parallel endpoint (see Deliverable 1).
- `LogDelay.delay_type` aggregation (Sprint 10's `get_delay_frequency_scoped()`) — Deliverable 2 ("which trade is most often delayed") is a **different cross-reference** than what exists: Sprint 10 groups delays by `delay_type` (weather, material_shortage, ...); Deliverable 2 needs delays cross-referenced against `LogTradeOnSite`/`LogWorkItem.trade` instead. `LogDelay` itself has no `trade` column — the join path (which trade was on site the day a delay happened? which trade's work item was blocked?) is a real design decision to make explicit during implementation, not assumed.
- `Permission.PROJECT_READ`/`DAILY_LOG_READ` (Sprint 8) — the `client` role already holds both (`app/core/permissions.py`), which is most of what "client-facing progress portal" (Deliverable 5) needs at the authorization layer. This sprint's real work for that deliverable is almost entirely about **what data a client-appropriate view should and shouldn't show** (e.g. safety incident details and cost data are plausibly staff-only even though a client can already read the underlying `DailyLog`) — not new RBAC infrastructure. Verify what Sprint 10's `frontend/src/auth/roles.ts` already gates before assuming new role sets are needed.
- `Project.company_id` (Sprint 6) — every analytics endpoint so far (`GET /projects/{id}/analytics`) is single-project. Nothing today aggregates across a company's multiple projects. Whether "Analytics Dashboard" means richer per-project views or a new company-wide cross-project view is a real, unresolved question — see Deliverable 6.

---

## Deliverables

### 1. Project Completion Trends (Extend, Don't Duplicate)

- Decide during implementation: does this deliverable mean the existing `get_completion_trend_scoped()` series rendered with more chart sophistication (e.g. a trend line with a projected-vs-actual overlay, using Sprint 11's `ScheduleTask`/`delay_adjusted_completion_date` as the "projected" side) — or a genuinely new metric? The roadmap's own wording ("project completion trends") most naturally reads as "what Sprint 10 already built," so the default assumption is: extend `AnalyticsPanel.tsx`'s existing "Completion trend" chart to also plot the project's `projected_completion_date`/`delay_adjusted_completion_date` (Sprint 11) as a reference line, giving a real actual-vs-planned view for the first time. Document whichever choice is made as an ADR either way, since "extend an existing chart" vs. "add a new one" changes what Deliverable 1 concretely ships.

### 2. Delay Pattern Analysis by Trade

- `DailyLogRepository.get_delay_frequency_by_trade_scoped()` (or similar) — for each approved log with at least one `LogDelay`, cross-reference against that same log's `LogTradeOnSite` rows (the trades present the day the delay happened) to produce (trade, delay_count, total_hours_lost) tuples, the trade-shaped counterpart to Sprint 10's delay-type-shaped aggregation.
- Decide during implementation which join is more meaningful: "trades on site the day of the delay" (broad — any trade present, whether or not their work was actually blocked) vs. "trades whose `LogWorkItem`/`LogWorkInProgress` rows were specifically named in `LogDelay.tasks_affected`" (narrow — `tasks_affected` is a free-text array per `LogDelay`'s doc comment, not a structured FK, so this path needs text matching against `LogWorkItem.task_description`, which is fragile). The broad join is almost certainly the pragmatic Sprint 13 choice; document why if the narrow one is attempted instead.
- `GET /projects/{id}/analytics` response gains a new field (e.g. `delay_frequency_by_trade`) rather than a new endpoint — matching how Sprint 11 added fields to the existing schedule response instead of proliferating endpoints for related, co-displayed data.

### 3. Safety Incident Trends

- `DailyLogRepository.get_safety_incident_trend_scoped()` — incident count over time (by `log_date`, approved logs only) plus a breakdown by `LogSafetyIncident.incident_type` and `osha_recordable` (the two fields most relevant to "is this getting better or worse, and is any of it OSHA-reportable"). `LogHazard` (identified-but-not-yet-incident hazards) is a related but distinct signal — decide during implementation whether hazard trends belong in this deliverable or are out of scope for Sprint 13 (the roadmap only names "safety incident trends," not hazards).
- New field on the analytics response (or a new endpoint if the response is getting large enough to warrant splitting — decide during implementation based on how Deliverables 1–3 actually compose).

### 4. Productivity by Stage and Trade

- The one deliverable needing a genuinely new metric definition: "productivity" isn't a field anywhere in the schema. The most defensible, data-grounded definition available without inventing new log fields: `LogWorkItem.task_completion_percent` averaged per `(current_stage, trade)` pair across a project's approved logs — "how much of the work items logged for this trade, in this stage, report as complete." Document the chosen definition as an ADR; this is exactly the kind of judgment call Sprint 11's variance-message wording and Sprint 12's auto-reorder-multiple formula were each documented for, and productivity is a more ambiguous term than either of those.
- Pure computation over existing data — no AI call, matching every analytics deliverable's existing posture (Sprint 10's `ProjectAnalyticsResponseData`, Sprint 11's `ADR-048`, Sprint 12's lead-time warnings all deliberately avoid an LLM here).

### 5. Client-Facing Progress Portal

- Primarily a **data-shaping and frontend** deliverable, not a new authorization system — see "What already exists" above. Decide during implementation exactly which of Deliverables 1–4's new fields a `client`-role user should see on `GET /projects/{id}/analytics` (all of them? a curated subset, e.g. completion trend and safety-incident-count-only, without granular incident detail?) and document the decision, the same way Sprint 10, Deliverable 7 documented which UI elements `client` should and shouldn't see.
- If a curated subset is chosen, this may need either (a) role-conditional fields in the same response (simplest, matches how `frontend/src/auth/roles.ts` already conditionally renders UI from one response), or (b) a role check inside the router that omits certain fields for non-staff roles — decide and document which, since (b) is a real backend behavior change while (a) is purely a frontend rendering choice over an unchanged response.
- Frontend: extend `AnalyticsPanel.tsx` (not a new component — this is the same panel, just with more series/sections) with the new charts from Deliverables 1–4, applying whatever client-facing curation Deliverable 5 decided on.

### 6. Company-Wide View — Decide Scope Before Building

- **Explicit open question, not an assumed deliverable:** does "Analytics Dashboard" mean richer per-project analytics (Deliverables 1–5 above, all still scoped to one project at a time, matching every existing analytics endpoint) or a new cross-project, company-wide dashboard (e.g. "average completion % across all active projects," "which project has the most delays this month")? The roadmap's five bullet points read naturally as per-project enrichment — none of them say "across projects" — so the default scope for this sprint is **per-project only**, with a company-wide view explicitly deferred as a candidate for a later sprint unless a concrete need surfaces during implementation. If it does surface, document the decision to pull it into this sprint as an ADR rather than silently expanding scope.

### 7. Tests

- `tests/test_db_repositories.py` (extended) or a new `tests/test_analytics_repository.py` — the new aggregation methods (delay-by-trade, safety trend, productivity), tenant scoping, correct math against small controlled fixtures (matching `tests/test_api_analytics.py`'s existing pattern of seeding a small, hand-built set of logs+delays and asserting exact aggregation results).
- `tests/test_api_analytics.py` (extended) — new response fields, the same two-company tenant-isolation pattern every Sprint 9–12 test file uses, and a client-role test confirming Deliverable 5's curation decision actually holds (if a curated subset was chosen).
- Frontend: extend `AnalyticsPanel.test.tsx` for the new chart sections.
- **Given every sprint from 9 through 12 found real, live-verification-only bugs** that no mock-based test caught (duplicate documents, PDF font corruption, missing RBAC gating, an attribute mismatch, an undercounted lag total, a transaction-isolation bug, a lossy dict reconstruction, a status masking a failure, and — closest precedent for this sprint — Sprint 10's own missing-RBAC-gating bug, found only by logging in as a real `client`-role user in a real browser) — continue verifying every deliverable live before considering it done, not just green tests. Deliverable 5 specifically needs a real `client`-role login in a real browser, the same check that caught Sprint 10's analogous bug.

---

## Constraints

- **No paid APIs, no paid SaaS, no AI/LLM calls for any analytics computation** — matches ADR-005/ADR-007's posture and every prior sprint's aggregation-over-generation choice for this category of feature.
- **Sprint 1–12 FROZEN.** Extend `app/`/`database/`/`frontend/`, do not rewrite Sprint 10's `get_completion_trend_scoped()`/`get_delay_frequency_scoped()`, Sprint 8's RBAC model, or any other prior sprint's code unless fixing a verified bug (see `docs/CONTRIBUTING.md` §5).
- **Maintain backward compatibility.** `GET /projects/{id}/analytics`'s existing two fields (`completion_trend`, `delay_frequency`) keep their exact current shape regardless of what new fields Deliverables 1–4 add alongside them.
- **Continue the "explain, implement, test, verify" per-subsystem discipline**, live verification over mock-based tests.
- **No new database tables.** Every deliverable in this sprint is a read-only query over data Sprints 6–12 already persist — if implementation discovers a genuine need for new schema, that is itself a decision to document as an ADR (why the existing schema wasn't sufficient), not something to build silently.

---

## Explicit Out of Scope for Sprint 13

- A company-wide, cross-project dashboard — see Deliverable 6; only pulled in if a concrete need surfaces during implementation, documented as an ADR if so
- Hazard trends (`LogHazard`, distinct from `LogSafetyIncident`) — only in scope if Deliverable 3's implementation finds a natural, low-cost way to include it; not a required part of "safety incident trends" as named by the roadmap
- Sprint 14's Cost Intelligence (daily cost tracking, budget-vs-actual, etc.) — a later sprint per `docs/ROADMAP.md`'s Phase 4 plan; `Project.contract_value_usd` and `LogMaterialUsed.unit_cost_usd`/`PurchaseOrder.unit_cost_usd` (Sprint 12) exist but are explicitly not aggregated into any cost view this sprint
- Real-time/streaming analytics, scheduled report emails, exportable analytics PDFs — no prior sprint has built a scheduler (Sprint 11's resume-audit-confirmed finding: no Celery Beat exists), and this sprint doesn't need one either since everything here is computed at request time
- Production Docker deployment, multi-company admin UI — still open per every prior sprint spec's own out-of-scope list, unless explicitly pulled forward
