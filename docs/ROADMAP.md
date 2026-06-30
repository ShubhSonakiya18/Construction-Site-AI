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

### Sprint 3 — Speech-to-Text ✅ (Pending Approval)
- Engine-agnostic `speech/` framework — Faster Whisper as the sole `BaseSTTEngine` implementation
- Audio validation (8 blocking checks + 3 warnings), normalization, optional noise reduction
- Timestamps, confidence scores, chunk-boundary metadata
- Language auto-detection (or forced via config)
- Structured `SpeechProcessingResult` output (JSON/JSONL/text export formats)
- `transcribe.py` CLI (single file, batch, dry-run)

### Sprint 4 — AI Information Extraction
- Qwen2.5 via Ollama integration
- Voice transcript → ConstructionDailyLog
- Prompt engineering for structured extraction
- JSON validation against schema
- Retry logic for invalid outputs
- Never store malformed JSON

### Sprint 5 — AI Generation Services
- Daily Report Generator
- Customer Progress Update Generator
- Safety Toolbox Talk Generator
- Material Reminder Generator
- All services independently testable
- Prompts stored separately from code

### Sprint 6 — Database Design
- PostgreSQL schema design
- SQLAlchemy ORM models
- Alembic migrations
- Seed scripts
- ER diagram
- All Sprint 1 schema sections → normalized tables

---

## Phase 2: Backend API (Sprints 7–8)
*Goal: Production-ready REST API*

### Sprint 7 — FastAPI Backend
- CRUD endpoints for all entities
- Audio upload endpoint
- AI pipeline orchestration endpoint (upload → transcribe → extract → generate)
- Background task processing (Celery or FastAPI background tasks)
- Input validation (Pydantic models from JSON Schema)
- Error handling and logging
- API documentation (auto-generated OpenAPI)

### Sprint 8 — Authentication and Multi-Tenancy
- JWT authentication
- User management (register, login, password reset)
- Company and project isolation
- Role-based access control (Admin, Foreman, Project Manager, Client)
- Secure audio file handling

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
| First working API | Sprint 7 | Audio upload via API returns all 5 AI outputs |
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
