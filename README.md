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
| API Framework | FastAPI (planned Sprint 7) | Async, automatic OpenAPI docs, production-ready |
| Database | PostgreSQL (planned Sprint 6) | Relational integrity for construction data |
| ORM | SQLAlchemy + Alembic (planned Sprint 6) | Type-safe models, version-controlled migrations |
| Speech-to-Text | Faster Whisper (local) | Free, open-weight, high accuracy, runs on CPU |
| AI Inference | Groq free-tier cloud API | llama-3.3-70b-versatile, zero token cost, no GPU required |
| Validation | JSON Schema draft-07 + business rules | Schema-first, language-agnostic |
| Containerization | Docker + Compose (planned Sprint 7) | Reproducible environments |

**No paid APIs.** Speech-to-text runs locally. Language model inference uses Groq's free tier.

## Sprint Progress

| Sprint | Title | Status |
|--------|-------|--------|
| Sprint 1 | Construction Research + Schema Design | ✅ Complete & Frozen |
| Sprint 2 | Synthetic Dataset Generation Framework | ✅ Complete & Frozen |
| Sprint 3 | Speech-to-Text Pipeline (Faster Whisper) | ✅ Complete & Frozen |
| Sprint 4 | AI Information Extraction (Groq + EngineFactory) | ✅ Complete — Pending Approval |
| Sprint 5 | AI Generation Services | Blocked — awaiting Sprint 4 approval |
| Sprint 6 | Database Design (PostgreSQL + Alembic) | Not started |

## Repository Structure

```
Construction-Site-AI/
├── knowledge/                    # FROZEN — domain model, schema, rules, ontology
├── dataset_generation_framework/ # Sprint 2 — synthetic data generators
├── speech/                       # Sprint 3 — Faster Whisper STT framework
├── extraction/                   # Sprint 4 — Groq extraction framework
├── docs/                         # Architecture docs, ADRs, changelog, roadmap
├── tests/                        # Full test suite (322 tests, no API key needed)
├── generate.py                   # CLI: generate synthetic datasets
├── transcribe.py                 # CLI: transcribe audio files
├── extract.py                    # CLI: extract ConstructionDailyLog from transcript
├── requirements-dev.txt          # All dependencies (Python 3.12+)
├── .env.example                  # Environment variable template
└── README.md
```

## Getting Started

```bash
# Python 3.12 required
pip install -r requirements-dev.txt

# Copy environment template and add your Groq API key (free at console.groq.com)
cp .env.example .env
# Edit .env: set GROQ_API_KEY=gsk_your_key_here

# Run the full test suite (no API key needed for unit tests)
pytest tests/ -v

# Extract from a transcript (requires GROQ_API_KEY in .env)
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
