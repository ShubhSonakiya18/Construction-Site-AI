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
| ORM | SQLAlchemy + Alembic | Type-safe models, version-controlled migrations |
| Speech-to-Text | Faster Whisper | Local, free, high accuracy multilingual |
| AI Inference | Ollama + Qwen2.5 | Local LLM, no API costs, production quality |
| Validation | Pydantic v2 | Runtime type safety for all AI outputs |
| Containerization | Docker + Compose | Reproducible environments, easy deployment |

**All AI runs locally. No paid APIs. No data leaves your infrastructure.**

## Sprint Progress

| Sprint | Title | Status |
|--------|-------|--------|
| Sprint 1 | Construction Research + Schema Design | ✅ Complete |
| Sprint 2 | Synthetic Dataset Generation | Pending |
| Sprint 3 | Speech-to-Text Pipeline | Pending |
| Sprint 4 | Information Extraction Engine | Pending |
| Sprint 5 | AI Services | Pending |
| Sprint 6 | Database Design | Pending |

## Repository Structure

```
Construction-Site-AI/
├── knowledge/          # Machine-readable domain knowledge and schemas
├── docs/               # Human-readable documentation per sprint
├── PROJECT_STATE.md    # Single source of truth for project status
└── README.md
```

## Getting Started

> Setup instructions will be added in Sprint 3 when the first runnable component is built.

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
