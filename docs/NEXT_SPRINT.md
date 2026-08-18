# Next Sprint: Sprint 10 — Reports and Client Portal

**Status:** READY TO BEGIN — Sprint 9 approved 2026-08-19 (see `docs/PROJECT_STATE.md`).
**Prerequisites:** Sprint 9 APPROVED and FROZEN — satisfied. PostgreSQL, Redis, and a running Celery worker (all Sprint 9 requirements) still apply.

---

## Sprint 10 Goal

Per `docs/ROADMAP.md`'s Phase 3 plan: give generated documents (daily report, customer update, safety talk, material reminder — all already produced by Sprint 5's `AIServiceManager` and stored via Sprint 6's `GenerationRepository`) a way to actually be *viewed, exported, and sent* — and give the `client` role (already defined in Sprint 8's RBAC, currently unused by any UI) a portal to see them in.

Nothing here requires new AI generation logic. Sprint 5's 4 services and `POST /daily-logs/{id}/generate` already produce and persist everything Sprint 10 displays — this sprint is surface area (frontend, export, a `GET /projects` list, a "mark sent" action), not new AI capability.

---

## Deliverables

### 1. `GET /projects` — List Projects for the Caller's Company

**Carried over from Sprint 9** (`docs/PROJECT_STATE.md`'s "Known, documented gap"): no endpoint lists a company's projects, so the Sprint 9 frontend's Dashboard requires a project ID typed in manually. `ProjectRepository.list_by_company()` (`database/repositories/project.py:61`) already exists and does the query — this is a thin router addition, not new repository logic.

- `GET /api/v1/projects` — `ProjectRepository.list_by_company()` takes a raw `company_id`, not a `TenantContext` (unlike `get_by_id_scoped`/`list_by_project_scoped`, which take `tenant=` and scope internally) — the router must derive `company_id` from `TenantContext.from_current_user(user).company_id` itself before calling it, the same way `Permission.PROJECT_READ` (already granted to every role including `client`) gates the route. Paginated like `GET /projects/{id}/daily-logs`.
- Frontend: replace `DashboardPage.tsx`'s manually-typed project ID with an actual picker populated from this endpoint. Keep the `localStorage`-remembered "active project" behavior for return visits.

### 2. View Generated Reports (Frontend)

`GET /daily-logs/{id}/outputs` (Sprint 7, already exists) returns all 4 `GenerationOutput` rows for a log — nothing new needed on the backend for viewing. Add to the frontend:

- A "Documents" tab/section on `LogReviewPage.tsx` listing the 4 generated documents (daily report, customer update, safety talk, material reminder) for that log, rendering each `content` field (Markdown for 3 of them, email-shaped text for `customer_update` — see `docs/AI_SERVICES.md` §3's `ServiceType` table for which is which).
- If a log has no outputs yet (never generated, or generation failed), surface a "Generate documents" action calling `POST /daily-logs/{id}/generate` — the endpoint already exists and is already permission-gated (`Permission.DAILY_LOG_GENERATE`) and rate-limited (Sprint 9's `enforce_ai_generation_rate_limit`).

### 3. Customer Progress Email — Preview and Send

- `POST /daily-logs/{id}/outputs/{output_id}/mark-sent` — a new, narrow endpoint. `GenerationOutput.is_sent`/`sent_at` columns already exist (`database/models/generation.py:184-191`) but nothing currently sets them; this endpoint sets them and returns the updated row. Gate behind a new `Permission.GENERATION_OUTPUT_SEND` (or reuse `DAILY_LOG_GENERATE` if a new permission is judged unnecessary — decide during implementation, document the choice as an ADR either way).
- **Explicitly out of scope:** actually emailing the customer_update content to the client. Reuse Sprint 9's `EmailSender` Protocol (`app/services/email_sender.py`) for this in a later sprint once there's a real "client contact email" field to send to — no such field exists on `Project`/`User` yet. This sprint only tracks "the PM confirmed this was sent" (e.g. sent via their own email client, copy-pasted), not delivery automation.
- Frontend: a "Preview" view for the customer_update output (rendered as it would appear in an email) with a "Mark as sent" button calling the new endpoint.

### 4. Safety Toolbox Talk PDF Export

- No PDF generation exists anywhere in this codebase yet — this is genuinely new capability, not surface area over existing logic. Evaluate `weasyprint` (HTML→PDF, pure Python, LGPL — free and open-source, consistent with this project's no-paid-services constraint) vs `reportlab` (lower-level, more control, also free/open-source) during implementation; document the choice as an ADR.
- `GET /daily-logs/{id}/outputs/{output_id}/pdf` — renders the `safety_talk` output's Markdown content to a styled PDF and returns it as a file download. Scope narrowly to `safety_talk` only for this sprint (the one Sprint 10 deliverable that specifically names PDF export); generalizing to all 4 output types is a natural follow-up, not required now.

### 5. Material Reminder Notification Interface

- No new backend endpoint — `material_reminder` outputs are already covered by Deliverable 2 (view generated reports) and Deliverable 3's `mark-sent` pattern generalizes to it directly (same endpoint, different `service_type`).
- Frontend: surface material_reminder outputs with urgency visually distinguished (the generated Markdown already includes priority levels per `docs/AI_SERVICES.md`'s `material_reminder.md` prompt spec — no new data needed, just render what's already there prominently).

### 6. Basic Analytics (Completion Trend, Delay Frequency)

- `GET /projects/{id}/analytics` — new endpoint, new lightweight repository queries (not a new subsystem): completion-percent-over-time from `DailyLog.overall_project_completion_percent` grouped by `log_date`, and delay frequency/hours-lost aggregated from `LogDelay` rows already linked to approved logs — the same data `list_recent_with_children_scoped()` (Sprint 9's grounded-Q&A retrieval) already knows how to fetch, but aggregated instead of stuffed into an LLM prompt.
- Frontend: a simple chart (a lightweight charting library — evaluate `recharts` vs `chart.js`, pick during implementation) on the Dashboard showing these two trends for the active project.

### 7. Client Portal

- No new role or permission model needed — Sprint 8's `client` role already exists with exactly the right scope (`DAILY_LOG_READ`, `PROJECT_READ`, `SESSION_MANAGE_OWN` — read-only, no approve/reject/generate/manage). This deliverable is: confirm the existing frontend (Dashboard + LogReviewPage, built in Sprint 9) already degrades correctly for a `client`-role user (no Approve/Reject buttons — `LogReviewPage.tsx`'s `REVIEWER_ROLES` check already excludes `client`; no "Record" nav item relevance, though nothing currently hides it — decide whether to hide record/generate UI for `client` users during implementation) rather than building a separate portal UI from scratch.
- If a genuinely separate, simplified client-facing view is wanted instead of "the same app with fewer buttons," that's a bigger frontend decision — flag it as a decision point before starting, the way Sprint 9's own spec flagged the task-queue/frontend split.

### 8. Tests

- `tests/test_api_projects_list.py` — `GET /projects` pagination, tenant scoping, empty-company case.
- `tests/test_api_generation_outputs.py` — `mark-sent` endpoint: permission gate, idempotency (marking an already-sent output sent again), 404 for wrong tenant/log.
- `tests/test_pdf_export.py` — safety_talk PDF generation produces a valid PDF (check magic bytes / a PDF-parsing library's ability to open it), handles a log with no safety_talk output gracefully (404, not a 500).
- `tests/test_api_analytics.py` — completion-trend and delay-frequency aggregation correctness against seeded/fixture data.
- Frontend: component tests for the new Documents view, project picker, and analytics chart, following Sprint 9's Vitest + Testing Library pattern (`frontend/src/pages/LoginPage.test.tsx` etc. as the reference shape).

---

## Constraints

- **No paid APIs, no paid SaaS.** PDF library and charting library must be free/open-source, matching the project's ADR-005/ADR-007 posture. Actual email delivery to clients (as opposed to marking sent) is out of scope regardless — see Deliverable 3.
- **Sprint 1–9 FROZEN.** Extend `app/`/`database/`/`frontend/`, do not rewrite Sprint 7-9's services/routers/schemas/pages unless fixing a verified bug (see `docs/CONTRIBUTING.md` §5 for the freeze-discipline pattern).
- **Maintain backward compatibility.** Every existing endpoint's request/response contract continues to work unchanged; `GenerationOutput.is_sent` defaulting to `False` and only settable via the new endpoint is additive, not a breaking schema change.
- **Continue the "explain, implement, test, verify" per-subsystem discipline**, and continue verifying live (not just against mocks) where Sprint 9 found real bugs precisely because of that — PDF export and email "send" tracking are exactly the kind of feature a mock-only test suite could report as passing while producing a corrupt PDF or a silently-never-fired action.

---

## Explicit Out of Scope for Sprint 10

- Real email delivery of the customer-update document to an actual client inbox (Deliverable 3 explains why — no client contact field exists yet)
- A fully separate, redesigned client-facing UI (vs. the existing app gated by the `client` role's existing permissions) — a decision point, not a default
- OSHA 300/301 auto-generation (Phase 5 per `docs/ROADMAP.md`)
- Mobile app (Phase 5)
- Multi-company admin UI, production Docker deployment, API keys for external clients (Sprint 10+/later, per the Sprint 8/9 specs' own out-of-scope lists — still not this sprint unless explicitly pulled forward)
