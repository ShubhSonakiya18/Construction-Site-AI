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
- 59 new tests; full suite 777 passing, 0 regressions
- `docs/BACKEND_ARCHITECTURE.md`, `docs/BACKEND_STARTUP.md`, `docs/CONTRIBUTING.md`

### Sprint 8 — Authentication and Multi-Tenancy
- User registration, password reset (Sprint 7 shipped login only, against one seeded dev account)
- Full role-based access control enforcement (Sprint 7 has `require_role()` wired on the review-approval endpoints only)
- Company and project isolation (row-level scoping by `company_id`, embedded in the JWT since Sprint 7)
- Celery + Redis replacing `BackgroundTasks` (extension point documented in `docs/BACKEND_ARCHITECTURE.md` §10)
- Secure audio file handling (S3-compatible storage — Sprint 7 uses local disk under `data/uploads/`)

---

## Phase 3: Frontend (Sprints 9–10)
*Goal: Usable web interface*

### Sprint 9 — React Frontend Core
- Login/logout flow
- Dashboard (active projects, recent logs)
- Voice recording interface (record directly in browser)
- Log review interface (review and approve AI-extracted logs)
- Responsive design (mobile-first — foresmen use phones)

### Sprint 10 — Reports and Client Portal
- View generated reports
- Customer progress email preview and send
- Safety toolbox talk PDF export
- Material reminder notification interface
- Basic analytics (completion trend, delay frequency)

---

## Phase 4: Intelligence (Sprints 11–14)
*Goal: Proactive AI features beyond daily logs*

### Sprint 11 — Scheduling Module
- Gantt chart generation from daily logs
- Schedule variance detection ("you're 5 days behind on framing")
- Critical path tracking
- Delay impact prediction

### Sprint 12 — Inventory and Procurement
- Material consumption tracking from daily logs
- Auto-generated purchase orders
- Lead time warnings ("order countertops now or miss your closing date")
- Supplier integration preparation

### Sprint 13 — Analytics Dashboard
- Project completion trends
- Delay pattern analysis (which trade is most often delayed?)
- Safety incident trends
- Productivity by stage and trade
- Client-facing progress portal

### Sprint 14 — Cost Intelligence
- Daily cost tracking
- Budget variance alerts
- Cost prediction (earned value management)
- Change order tracking

---

## Phase 5: Advanced AI (Future)
*Goal: Differentiated AI capabilities that justify premium pricing*

### Defect Detection
- Upload photo → AI identifies potential defects
- Computer vision models (YOLO or similar)
- Defect flagged in daily log automatically
- Trend: "three concrete defects this month in garage slab"

### Bid Estimation
- Historical project data → bid estimate for new project
- Material quantity estimating from plans
- Labor hour estimates by trade and stage

### Autonomous Safety Compliance
- Daily log → automatic OSHA 300 log entries
- Incident report generation
- Safety trend analysis and proactive warning

### Voice Note Multi-Language Support
- Spanish, Portuguese, Mandarin, French support
- Critical for USA residential construction workforce demographics

---

## Technical Milestones

| Milestone | Sprint | Description |
|-----------|--------|-------------|
| First AI extraction | Sprint 4 | Voice note → ConstructionDailyLog end-to-end |
| First working API | Sprint 7 ✅ | Audio upload via API queues the full pipeline; poll for status; retrieve the daily log + all 4 AI outputs |
| First working UI | Sprint 9 | Can record voice note in browser and see results |
| Multi-tenant ready | Sprint 8 | Multiple companies isolated |
| Production deploy | Sprint 10+ | Docker Compose deployment with proper secrets management |
| OSHA compliance | Phase 5 | Auto-generate OSHA 300/301 records |
| Mobile app | Phase 5 | React Native app for foreman in the field |

---

## Business Context

**Target Customer:** Residential general contractors with 5–50 active projects.
**Problem Solved:** Foremen spend 30–60 minutes per day on paperwork. This product makes it a 2-minute voice note.
**Pricing Model (Planned):** $99–$299/month per company (SaaS subscription).
**Competitive Advantage:** Fully local AI means construction companies can use it without their job site data going to a cloud API. This matters for privacy-conscious contractors.
