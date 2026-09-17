# Product Roadmap — Construction Site AI

**Vision:** The default daily reporting tool for residential construction companies in North America.

---

## Phase 1: Core AI Pipeline (Sprints 1–6)
*Goal: Voice note → structured database records*

### Sprint 1 — Foundation ✅
- Construction domain knowledge base
- Master ConstructionDailyLog schema
- Construction rules, dependency graph, validation rules, ontology

### Sprint 2 — Data Foundation ✅
- 5 synthetic datasets
- Dataset generators (Python scripts)
- 5,000 daily logs, 1,000 schedules, 500 materials, 1,000 customer emails, OSHA safety talks

### Sprint 3 — Speech-to-Text ✅
- Engine-agnostic `speech/` framework — Faster Whisper as the sole `BaseSTTEngine` implementation
- Audio validation (8 blocking checks + 3 warnings), normalization, optional noise reduction
- Timestamps, confidence scores, chunk-boundary metadata
- Language auto-detection (or forced via config)
- Structured `SpeechProcessingResult` output (JSON/JSONL/text export formats)
- `transcribe.py` CLI (single file, batch, dry-run)

### Sprint 4 — AI Information Extraction ✅
- Provider-agnostic `extraction/` framework — `GroqEngine` as the sole `BaseLLMProvider` implementation; `EngineFactory` registry for zero-business-logic provider switching
- `ExtractionPipeline.extract(transcript_text) -> ExtractionResult`
- Prompt engineering: `PromptBuilder` with schema-derived enum context, editable `system_prompt.txt`
- 3-strategy JSON repair for LLM output (direct, markdown fence, brace scan)
- Two-stage validation: JSON Schema + Sprint 2 `ValidationPipeline` (`applies_to="ai_extraction"`)
- Per-field confidence scores, retry with exponential backoff
- `extract.py` CLI; full test suite with `MockExtractionEngine` (no API key needed)

### Sprint 5 — AI Generation Services ✅
- `generation/` package: `AIServiceManager` orchestrator, 4 typed services (`DailyReportService`, `CustomerUpdateService`, `SafetyTalkService`, `MaterialReminderService`)
- Pydantic output models: `DailyReport`, `CustomerUpdate`, `ToolboxTalk`, `MaterialReminder`, `GenerationResult`
- Versioned `.md` prompt files with YAML-like frontmatter (`generation/prompts/`)
- `ContentValidator` — 6 AI output quality checks (empty, length, sections, placeholders, duplicates, markdown)
- `ServiceMetadata` observability: provider, model, tokens, response time, retry count, prompt version
- `EngineFactory` reused via duck typing — no Sprint 4 modifications
- `report.py` CLI; 164 tests, all passing without GROQ_API_KEY (mock DI)
- `docs/AI_SERVICES.md` complete reference

### Sprint 6 — Database Design ✅ COMPLETE
- 26 SQLAlchemy 2.x ORM models (Mapped[T] style)
- 4 composable mixins (UUID PK, Timestamp, SoftDelete, AuditUser)
- 9 typed repository classes (BaseRepository[T] + 8 domain repositories)
- Alembic initial migration — PostgreSQL-native JSONB/UUID/TIMESTAMPTZ
- Idempotent reference data seed (25 trades, 22 stages, 16 material cats, 16 PPE types)
- Fixed-UUID sample data seed (demo company + project + daily log)
- 123 new tests (SQLite in-memory), 718 total passing, 0 regressions
- `docs/DATABASE_ARCHITECTURE.md` — ER diagram, ADR-026–030, migration guide

---

## Phase 2: Backend API (Sprints 7–8)
*Goal: Production-ready REST API*

### Sprint 7 — FastAPI Backend ✅ COMPLETE
- Application factory pattern (`app/create_app.py`), `/api/v1` versioned routing
- JWT login (`POST /auth/login`) — registration/reset deferred to Sprint 8
- Audio upload endpoint + status polling
- AI pipeline orchestration via `BackgroundTasks` (upload → transcribe → extract → generate), Celery migration path documented
- Daily-log review lifecycle endpoints, delegating to the frozen Sprint 6 repository state machine
- Standardized response envelope (`success`, `message`, `data`, `metadata`, `errors`, `timestamp`, `request_id`) on every endpoint
- Centralized exception handling, structured request logging (never logs secrets)
- 4 health endpoints: `/health` (full diagnostic), `/live`, `/ready`, `/version`
- Auto-generated OpenAPI docs (`/docs`, `/redoc`) with custom title/description/contact metadata
- 59 new tests; full suite 801 passing, 0 regressions
- `docs/BACKEND_ARCHITECTURE.md`, `docs/BACKEND_STARTUP.md`, `docs/CONTRIBUTING.md`

### Sprint 8 — Authentication, Authorization & Multi-Tenant Hardening ✅ COMPLETE
- Opaque, server-backed refresh tokens with rotation (`user_sessions` table); logout, logout-all-devices, password change/reset all revoke sessions correctly
- RBAC permission layer (`Permission` enum + `ROLE_PERMISSIONS`) — all 9 relevant endpoints now permission-gated (7 previously had none); existing 6 roles preserved, `system_admin` added
- Repository-layer multi-tenancy scoping (`TenantScopedRepository`) — company_id enforced automatically, never trusts client-supplied values; cross-tenant access returns 404, audited `system_admin` bypass
- Full user management: create/list/get/update-profile/deactivate/restore/assign-role/unlock, with a role-assignment hierarchy and last-admin protection
- Security hardening: account lockout (5 attempts/15 min, configurable), rate limiting on login + forgot-password (in-memory, Redis-swappable), security response headers
- Structured audit logging: `AuditLog` extended with first-class queryable columns, 20+ event types, fail-open by design (one deliberate exception for cross-tenant access)
- 121 new tests; full suite 913 passing, 0 regressions; live-verified against real PostgreSQL for every subsystem
- `docs/AUTHENTICATION_ARCHITECTURE.md`, `docs/AUTHORIZATION_ARCHITECTURE.md`
- **Deferred to Sprint 9 (delivered — see below):** Celery + Redis task queue, real email delivery for password reset (Sprint 8 focused on auth/authz, not infrastructure — see `docs/CHANGELOG.md` [Sprint 8]). S3-compatible audio storage remains deferred past Sprint 9 — not part of what was actually built; local disk storage (`data/uploads/`) continues as-is.

---

## Phase 3: Frontend (Sprints 9–10)
*Goal: Usable web interface*

### Sprint 9 — Task Queue, Email Delivery, and React Frontend Core ✅ APPROVED & FROZEN (2026-08-19)
- Celery + Redis replacing `BackgroundTasks` (extension point documented in `docs/BACKEND_ARCHITECTURE.md` §10) — `run_pipeline()` itself unchanged, retry policy added at the Celery task wrapper (ADR-043)
- Real email delivery for the Sprint 8 password-reset flow: `EmailSender` Protocol, SMTP or dev-console (ADR-045); raw-token-in-response is now explicit opt-in, not environment-implicit
- Sprint 8's in-memory `RateLimiter` migrated to `RedisRateLimiter` (ADR-041's planned migration, delivered — ADR-044, Lua-script atomicity verified with a real concurrent-requests test)
- React frontend core (built in the same sprint, not split — see `docs/NEXT_SPRINT.md`'s decision point):
  - Login/logout flow, forgot/reset password
  - Dashboard (daily-log list + grounded Q&A, ADR-042)
  - Voice recording interface (`MediaRecorder`, record directly in browser)
  - Log review interface (review and approve/reject AI-extracted logs)
  - Responsive design (mobile-first — foremen use phones)
- 957 backend tests + 15 frontend tests passing; every deliverable also verified live (real Redis, real Celery worker, real emailed link, real Playwright browser session) — not just against mocks
- **Known gap carried to Sprint 10:** no `GET /projects` list endpoint yet — Dashboard takes a project ID typed in directly. **Resolved in Sprint 10** — see below.

### Sprint 10 — Reports and Client Portal ✅ APPROVED & FROZEN (2026-09-15)
- View generated reports — `DocumentsPanel.tsx`, plus a Regenerate action. Found and fixed a real bug where regenerating showed every historical document instead of the current 4 (`GenerationRepository.list_latest_for_log()`)
- Customer progress email preview and send — `mark-sent` tracking endpoint; real delivery stays deferred (no client contact field exists yet)
- Safety toolbox talk PDF export — `app/services/pdf_export.py` (`reportlab`, ADR-046). Found and fixed a real Unicode-glyph-corruption bug on the first live download
- Material reminder notification interface — `MaterialReminderContent.tsx`, color-coded CRITICAL/HIGH/MEDIUM/LOW priority badges
- Basic analytics (completion trend, delay frequency) — `GET /projects/{id}/analytics`, rendered with `recharts`
- Also closed the `GET /projects` gap Sprint 9 carried forward, and found/fixed a real frontend RBAC gap (Generate/Mark-as-sent/Record shown to roles that would 403 on click)
- 997 backend tests + 66 frontend tests passing; every deliverable verified live, including a real `client`-role login through a real browser
- Approved 2026-09-15 during a resume-audit after a pause — the 2026-08-19 approval commit had asserted approval without actually applying it; all 7 deliverables were independently re-verified live before the status was corrected

---

## Phase 4: Intelligence (Sprints 11–15)
*Goal: Proactive AI features beyond daily logs*

### Sprint 11 — Scheduling Module ✅ APPROVED & FROZEN (2026-09-16)
- `ProjectSchedule`/`ScheduleTask` tables — migration `005_scheduling.py`, one schedule per project, seeded from `knowledge/dependency_graph.json`'s 23-node sequence
- Gantt chart generation — `GET /projects/{id}/schedule`, hand-rolled SVG Gantt (`SchedulePanel.tsx`), no third-party charting library
- Schedule variance detection ("you're N days behind on framing") — pure date arithmetic, no AI call
- Critical path tracking — a real per-project CPM forward/backward pass including inter-task lag, computed once at schedule-creation time; deliberately diverges from the knowledge file's own generic "typical" path when a project's real computation finds a longer branch (by design, not a bug)
- Delay impact prediction — forward graph-walk propagation of critical-path-impacting delays, computed live on every schedule read, never persisted
- Actual dates now populate automatically from approved daily logs (the piece that makes variance detection meaningful)
- 4 real bugs found and fixed during implementation/live verification (an attribute-name mismatch, an undercounted lag in the critical-path total, a transaction-isolation bug that could have silently undone a log approval, and a read-only computation that mutated real database-tracked objects in place)
- 1036 backend tests + 82 frontend tests passing; every deliverable verified live against the real backend/database and, for the Gantt chart, a real Playwright browser session

### Sprint 12 — Inventory and Procurement ✅ APPROVED & FROZEN (2026-09-16)
- `InventoryItem`/`PurchaseOrder` tables — migration `006_inventory.py`, project-scoped inventory reconciled from approved daily logs' materials_used/delivered
- Material consumption tracking — automatic on log approval, same transaction-isolation pattern Sprint 11's schedule hook established
- Auto-generated purchase orders — draft POs created at reorder_point, deduplicated against already-open suggestions
- Lead-time warnings ("order countertops now or miss your closing date") — deterministic date arithmetic cross-referenced against Sprint 11's real schedule, no AI call
- Supplier integration preparation — plain-string supplier fields only, no real API integration, no speculative `suppliers` table
- 1067 backend tests + 97 frontend tests passing; every deliverable verified live against the real backend/database and, for the frontend panel, a real Playwright browser session

### Sprint 13 — Analytics Dashboard ✅ APPROVED & FROZEN (2026-09-16)
- Project completion trends — `projected_completion_date`/`delay_adjusted_completion_date` added to the existing analytics response from Sprint 11's schedule, shown as a text summary rather than a graphical reference line (categorical x-axis)
- Delay pattern analysis by trade — trades credited with a delay when present the day it happened, a broad join over text-matching free-text fields
- Safety incident trends — incident count over time and by type, with an explicit distinction between "not yet assessed" and "assessed as not OSHA-recordable"
- Productivity by stage and trade — average reported work-item completion percent per (stage, trade), deliberately not labeled a comparable "productivity" rate
- Client-facing progress portal — frontend-only curation hiding two staff-internal sections from the `client` role, same response to every role at the API layer
- Company-wide view explicitly decided against this sprint — no concrete need surfaced, and it would risk leaking cross-client data
- No new tables — every deliverable aggregates data Sprints 6–12 already persist
- 1081 backend tests + 116 frontend tests passing; every deliverable verified live against the real backend/database and, for the client-role curation, a real Playwright browser session logged in as a real client-role user

### Sprint 14 — Cost Intelligence ✅ APPROVED & FROZEN (2026-09-16)
- Daily cost tracking — extraction prompt widened for `financials` (already fully defined in `knowledge/construction_daily_log_schema.json`, never previously asked of the LLM); daily/cumulative totals computed server-side, never trusted from the model
- Budget variance alerts — computed status field (on_track/approaching_budget/over_budget/no_budget_set) against `Project.contract_value_usd`, not a pushed notification (no scheduler exists)
- Cost prediction (earned value management) — PV/EV/AC/CPI/SPI, EV reusing the same completion percent already shown elsewhere in analytics, PV assuming linear cost accrual across the schedule (a documented simplification)
- Change order tracking — new `LogChangeOrder` table (migration `007`), the one exception to `client_communication` staying JSON, because a change order's approval status mutates after its log is already frozen
- No new tables except `log_change_orders`; two real bugs (a Decimal/float type mismatch, a stale-completion-percent lookup) found and fixed via live verification against the real database, not caught by the test suite alone
- 1124 backend tests + 124 frontend tests passing; every deliverable verified live against real Groq extractions and the real database, including a real Playwright browser session confirming the client role still sees none of the cost data

### Sprint 15 — Autonomous Safety Compliance ✅ APPROVED & FROZEN (2026-09-17)
- OSHA classification data capture — 7 new columns on `LogSafetyIncident` (migration `008`); classification stays human-entered (never LLM-inferred, given the legal weight of a wrong government-form determination), day counts are voice-extractable
- Worker identification — exact full-name matching only (no fuzzy matching) to link incident reports to real `Worker` records for job-title reporting
- OSHA 300/301 PDF generation — `GET /projects/{id}/osha-300-log`, a genuinely new tabular PDF-rendering path (Sprint 10's exporter is Markdown-bullet-only), gated so the client role can't pull an internal compliance document
- Safety trend analysis and proactive warning — unresolved-hazard warnings, days since last incident, and an OSHA incidence rate withheld below a reliability floor rather than shown as a misleadingly precise number; "proactive warning" means a computed field on a read, not a pushed notification (no scheduler/notification infra exists)
- A live, pipeline-crashing extraction-prompt bug found and fixed just before this sprint began, making its own premise (real safety incident/hazard data actually existing) possible
- 1185 backend tests + 129 frontend tests passing; every deliverable verified live against real Groq extractions, a real applied migration, a real generated PDF opened and visually inspected, and real Playwright browser sessions

### Sprint 16 — Voice Note Multi-Language Support ✅ APPROVED & FROZEN (2026-09-17)
- English-normalized extraction — every voice note is transcribed in its spoken language by Whisper's own auto-detection, then translated to English during extraction via a system-prompt rule, so downstream fields, search, and generated documents stay uniformly English regardless of the foreman's language
- Detected-language surfacing — `GET /audio/{id}/status` and `RecordPage.tsx` show the detected language once transcription completes, with no UI change at all for English recordings
- A live, feature-disabling config bug (`SPEECH_WHISPER_LANGUAGE=en` forcing every recording to be mis-transcribed as English) found and fixed during the final live-verification step — the earlier direct-pipeline checks had bypassed `.env` entirely and could not have caught it
- No new tables, no translation-quality UI, no non-English document generation
- 1191 backend tests + 131 frontend tests passing; verified live with a real Spanish `.wav` fixture through the real upload API end-to-end, both before and after the config fix

### Sprint 17 — Reference-Cost Project Estimator ✅ APPROVED & FROZEN (2026-09-17)
- Both roadmapped Phase 5 items (Defect Detection, Bid Estimation) investigated and found genuinely blocked: Defect Detection has no photo-upload infrastructure or verified vision-capable model anywhere in this codebase; Bid Estimation's "historical project data" premise is unsupportable with the single project that exists in the database
- Materials-only reference-cost range estimator built instead on real existing data — `knowledge/cost_estimation_reference.json` (new typical-quantity reference file) combined with `knowledge/construction_ontology.json`'s material cost ranges and a project's real `ScheduleTask` stages (Sprint 11) and `project_size_sqft`
- Deliberately no labor-hour estimation — no defensible reference source for labor rates exists anywhere in this dataset; a materials-only estimate, honestly labeled, was chosen over a fabricated labor figure (ADR-065)
- `GET /projects/{id}/analytics` gains `cost_estimate`; `AnalyticsPanel.tsx` gains a staff-only "Reference cost estimate" section — every label makes clear this is a reference range, never a bid, a quote, or a claim of learning from historical projects
- No new tables — the estimate follows the same read-time-only projection pattern as Sprint 13's variance fields, Sprint 14's EVM, and Sprint 15's safety warnings
- 1205 backend tests + 135 frontend tests passing; every deliverable verified live against the real seeded project's real schedule/size/contract-value data, a real running API, and a real Playwright browser session

### Sprint 18 — Playwright E2E Suite and a Real requirements.txt ✅ APPROVED & FROZEN (2026-09-17)
- Both Phase 5 items re-checked and still blocked as Sprint 17 found them — scoped around real process/tooling debt instead: `docs/RESUME_AUDIT_2026-09-15.md` (2026-09-15) had flagged two gaps no sprint since had touched
- `requirements.txt` — a real, runtime-only dependency manifest separate from `requirements-dev.txt`, live-verified by a clean-venv install and a real server start
- `frontend/e2e/` — the first real, checked-in Playwright suite this project has had (8 specs), replacing the ad-hoc throwaway scripts every sprint from 9 through 17 used for "verified live" claims; a real `npm run test:e2e` script and `docs/E2E_TESTING.md`
- Two real bugs found and fixed while actually running the new suite: a login-rate-limit collision from logging in fresh per spec (fixed with a shared, once-authenticated session), and a vitest/Playwright test-collection collision (fixed with a `vite.config.ts` exclude)
- Docker Compose explicitly descoped — the development machine's C: drive had 0 bytes free at scoping time, so a real `docker-compose up` could not be live-verified; remains Open in `docs/DECISIONS.md`'s Pending Decisions table
- Pure tooling/process work, no product feature change; 1205 backend + 135 frontend + 8/8 E2E specs passing

### Sprint 19 — Proactive Alert Notifications ✅ APPROVED & FROZEN (2026-09-17)
- Both Phase 5 items re-checked and still blocked; picked up a real candidate surfaced during Sprint 18's own scoping instead
- Closes a gap Sprint 14's budget-variance status and Sprint 15's safety proactive-warnings both explicitly deferred ("no scheduler or notification infrastructure") — using entirely existing infrastructure: Celery Beat (already-pinned `celery` package) and the real `EmailSender` (Sprint 9)
- `project_alerts_sent` table (migration `009`) + `app/services/alert_service.py`'s dedup/cooldown decision logic (ADR-066) — a real status transition always fires regardless of cooldown, the same bad status persisting re-fires only after 24h
- `app/tasks/alert_tasks.py`'s hourly Celery Beat task, alerting every staff-role user in the affected company via real email
- `alert_history` on `GET /projects/{id}/analytics` + a staff-only "Alert history" section on `AnalyticsPanel.tsx`
- Unusually thorough live verification for a scheduled/background feature: a real Celery Beat process (run at a shortened interval for verification only) observed enqueueing the task twice on its own schedule, with the second run's alert correctly suppressed by the dedup logic — not just a unit test in isolation
- 1218 backend tests + 138 frontend tests passing

---

## Phase 5: Advanced AI (Future)
*Goal: Differentiated AI capabilities that justify premium pricing*

### Defect Detection
- Upload photo → AI identifies potential defects
- Computer vision models (YOLO or similar)
- Defect flagged in daily log automatically
- Trend: "three concrete defects this month in garage slab"
- **Investigated in Sprint 17, still blocked:** no photo/image upload infrastructure exists anywhere in this codebase, and no vision-capable model is verified to work with the currently configured Groq model — a real attempt needs both built first, not a contained gap.

### Bid Estimation
- Historical project data → bid estimate for new project
- Material quantity estimating from plans
- Labor hour estimates by trade and stage
- **Investigated in Sprint 17, still blocked on real historical data:** exactly one project exists in the database, so a genuine "historical project data → estimate" feature has nothing to learn from; generating synthetic seed projects to fill the gap would be circular. Sprint 17 built the honestly-buildable adjacent piece instead — a deterministic materials-only reference-cost range from typical-quantity data (see that sprint's entry above, ADR-065). Revisit this item once real multi-project historical data exists.

---

## Technical Milestones

| Milestone | Sprint | Description |
|-----------|--------|-------------|
| First AI extraction | Sprint 4 | Voice note → ConstructionDailyLog end-to-end |
| First working API | Sprint 7 ✅ | Audio upload via API queues the full pipeline; poll for status; retrieve the daily log + all 4 AI outputs |
| First working UI | Sprint 9 ✅ | Can record voice note in browser, upload, poll pipeline status, and review the result — verified live in a real browser session |
| Multi-tenant ready | Sprint 8 ✅ | Companies isolated at the repository layer; cross-tenant access returns 404; RBAC + audit logging in place |
| Production deploy | Sprint 10+ | Docker Compose deployment with proper secrets management |
| OSHA compliance | Sprint 15 ✅ | OSHA 300 Log PDF generation, safety classification fields, proactive hazard/incidence-rate warnings |
| Multi-language voice notes | Sprint 16 ✅ | Any spoken language auto-detected and translated to English during extraction; detected language surfaced in the UI |
| Mobile app | Phase 5 | React Native app for foreman in the field |

---

## Business Context

**Target Customer:** Residential general contractors with 5–50 active projects.
**Problem Solved:** Foremen spend 30–60 minutes per day on paperwork. This product makes it a 2-minute voice note.
**Pricing Model (Planned):** $99–$299/month per company (SaaS subscription).
**Competitive Advantage:** Fully local AI means construction companies can use it without their job site data going to a cloud API. This matters for privacy-conscious contractors.
