# Construction Site AI

A production-grade AI SaaS application that converts construction foreman voice recordings into structured site intelligence.

## What It Does

A foreman records one voice note per evening. The system converts it into:

- **Structured Daily Site Log** — Machine-readable JSON record
- **Customer Progress Update** — Professional email to the client
- **Safety Toolbox Talk** — OSHA-aligned safety briefing for tomorrow's crew
- **Material Reminder** — Procurement alert for needed materials
- **Database Records** — Structured storage for analytics and reporting

## Tech Stack

| Layer | Technology | Reason |
|-------|-----------|--------|
| Language | Python 3.12 | Type hints, modern async, AI ecosystem |
| API Framework | FastAPI | Async, automatic OpenAPI docs, production-ready |
| Database | PostgreSQL | Relational integrity for construction data |
| ORM | SQLAlchemy 2.x + Alembic | Type-safe models, version-controlled migrations |
| Speech-to-Text | Faster Whisper (local) | Free, open-weight, high accuracy, runs on CPU |
| AI Inference | Groq free-tier cloud API | llama-3.3-70b-versatile, zero token cost, no GPU required |
| Validation | JSON Schema draft-07 + business rules | Schema-first, language-agnostic |
| Auth | JWT (access tokens) + opaque server-backed refresh tokens | Stateless verification for hot paths, revocable sessions for logout/lockout |
| Containerization | Docker + Compose (planned) | Reproducible environments |

**No paid APIs.** Speech-to-text runs locally. Language model inference uses Groq's free tier.

## Sprint Progress

| Sprint | Title | Status |
|--------|-------|--------|
| Sprint 1 | Construction Research + Schema Design | ✅ Complete & Frozen |
| Sprint 2 | Synthetic Dataset Generation Framework | ✅ Complete & Frozen |
| Sprint 3 | Speech-to-Text Pipeline (Faster Whisper) | ✅ Complete & Frozen |
| Sprint 4 | AI Information Extraction (Groq + EngineFactory) | ✅ Complete & Frozen |
| Sprint 5 | AI Generation Services (4 services, report.py CLI) | ✅ Complete & Frozen |
| Sprint 6 | Database Design (PostgreSQL + SQLAlchemy + Alembic) | ✅ Complete & Frozen |
| Sprint 7 | Production FastAPI Backend | ✅ Complete & Frozen |
| Sprint 8 | Authentication, Authorization & Multi-Tenant Hardening | ✅ Complete — Pending Approval |

See `docs/PROJECT_STATE.md` for the full, evolving state and `docs/HANDOVER.md` for a complete project handover.

## API Overview

The backend (`app/`) exposes a versioned REST API under `/api/v1`:

- **Auth** — login, refresh, logout, logout-all, change/forgot/reset password, current user
- **Users** — create, list, get, update profile, deactivate/restore, assign role, unlock account
- **Audio** — upload a voice recording, poll processing status
- **Daily Logs** — retrieve, submit/approve/reject, trigger AI document generation
- **Projects** — list a project's daily logs
- **Health** — full diagnostic, liveness, readiness, version

Every endpoint enforces authentication (JWT), authorization (RBAC permission checks), and multi-tenancy scoping (a user can never access another company's data). See `docs/AUTHENTICATION_ARCHITECTURE.md`, `docs/AUTHORIZATION_ARCHITECTURE.md`, and `docs/BACKEND_ARCHITECTURE.md` for the full design.

## Repository Structure

```
Construction-Site-AI/
├── knowledge/                    # FROZEN — domain model, schema, rules, ontology
├── dataset_generation_framework/ # Sprint 2 — synthetic data generators
├── speech/                       # Sprint 3 — Faster Whisper STT framework
├── extraction/                   # Sprint 4 — Groq extraction framework
├── generation/                   # Sprint 5 — AI document generation services
├── database/                     # Sprint 6 — SQLAlchemy models, repositories, Alembic migrations
├── app/                          # Sprint 7/8 — FastAPI backend: routers, services, auth, RBAC
├── docs/                         # Architecture docs, ADRs, changelog, roadmap
├── tests/                        # Full test suite (913 tests, no API key needed for unit tests)
├── generate.py                   # CLI: generate synthetic datasets
├── transcribe.py                 # CLI: transcribe audio files
├── extract.py                    # CLI: extract ConstructionDailyLog from transcript
├── report.py                     # CLI: generate AI documents from a daily log
├── requirements-dev.txt          # All dependencies (Python 3.12+)
├── .env.example                  # Environment variable template
└── README.md
```

## Getting Started

```bash
# Python 3.12 required
pip install -r requirements-dev.txt

# Copy environment template and set required variables
cp .env.example .env
# Edit .env: set GROQ_API_KEY (free at console.groq.com), DATABASE_URL, JWT_SECRET_KEY

# Run the full test suite (no live database or API key needed — SQLite in-memory)
pytest -v

# Run the API server locally (see docs/BACKEND_STARTUP.md for full setup)
python -m uvicorn app.main:app --reload

# Extract from a transcript directly via CLI (requires GROQ_API_KEY in .env)
python extract.py --text "Today we had 6 workers. Poured the foundation slab. Sunny weather."

# Check engine availability
python extract.py --check
```

## Project Goal

Design this system for residential construction companies. Architecture must support future modules:
- Defect Detection (computer vision)
- Progress Monitoring (timeline tracking)
- Scheduling (Gantt and critical path)
- Bid Estimation (AI-assisted quotes)
- Cost Prediction (budget forecasting)
- Inventory Prediction (material planning)

## License

Proprietary. All rights reserved.
