# Next Sprint: Sprint 7 — FastAPI REST API

**Status:** AWAITING SPRINT 6 APPROVAL — Do not begin until Sprint 6 is approved.
**Prerequisites:** Sprint 6 APPROVED and FROZEN
**Supersedes:** Sprint 6 spec (now complete — see `database/` package and `docs/DATABASE_ARCHITECTURE.md`)

---

## Sprint 7 Goal

Build the production REST API layer that exposes all Sprint 1-6 capabilities as HTTP endpoints: audio upload, pipeline orchestration, daily log management, and AI report retrieval. This is the first user-facing layer — all previous sprints are infrastructure and library code.

---

## Deliverables

### 1. FastAPI Application

```
backend/
├── __init__.py
├── main.py               # FastAPI app, lifespan, CORS, exception handlers
├── config.py             # BackendConfig (from_env)
├── dependencies.py       # get_session(), get_current_user() DI
├── routers/
│   ├── auth.py           # POST /auth/login
│   ├── audio.py          # POST /audio/upload, GET /audio/{id}/status
│   ├── daily_logs.py     # Full CRUD + review lifecycle
│   ├── projects.py       # Project + Site CRUD
│   └── generation.py     # Trigger + retrieve AI outputs
└── schemas/              # Pydantic request/response models (separate from ORM models)
    ├── auth.py
    ├── audio.py
    ├── daily_log.py
    ├── project.py
    └── generation.py
```

### 2. Core Endpoints (MVP)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/login` | None | Returns JWT access token |
| POST | `/audio/upload` | Bearer | Upload audio → trigger pipeline |
| GET | `/audio/{id}/status` | Bearer | Poll processing status |
| GET | `/daily-logs/{id}` | Bearer | Get DailyLog with all children |
| GET | `/projects/{id}/daily-logs` | Bearer | List logs for a project |
| POST | `/daily-logs/{id}/submit` | Bearer | Submit draft for review |
| POST | `/daily-logs/{id}/approve` | Bearer (PM) | Approve log |
| POST | `/daily-logs/{id}/reject` | Bearer (PM) | Reject with notes |
| POST | `/daily-logs/{id}/generate` | Bearer | Trigger AI generation |
| GET | `/daily-logs/{id}/outputs` | Bearer | Get all GenerationOutputs |
| GET | `/health` | None | DB + service health check |

### 3. Authentication

- JWT access tokens (python-jose or PyJWT, both free/open source)
- POST `/auth/login` with `{email, password}` → `{access_token, token_type}`
- Middleware validates Bearer token on all protected routes
- Roles: `owner`, `admin`, `project_manager`, `foreman`
- Sprint 7 scope: Basic JWT only. No registration, no password reset.

### 4. Async Pipeline Integration

- Audio upload stores `AudioFile` row, queues background processing
- Background task: validate → transcribe (Whisper) → extract (Groq) → create DailyLog → generate reports
- FastAPI `BackgroundTasks` for Sprint 7; Celery deferred to Sprint 8
- Status polling reads `audio_files.processing_status`

### 5. Async Database

- `database/session.py` gains `get_async_session()` using `asyncpg` (already installed in Sprint 6)
- All FastAPI endpoints use `AsyncSession`; Sprint 1-6 CLI tools continue using sync `Session`
- SQLAlchemy 2.x supports both sync and async from the same `Base`

### 6. OpenAPI Docs

- Auto-generated Swagger UI at `/docs`
- ReDoc at `/redoc`
- All endpoints documented with request/response examples

### 7. Tests

- `tests/test_api_auth.py` — login success, wrong password, JWT expiry
- `tests/test_api_audio.py` — upload, status, pipeline trigger
- `tests/test_api_daily_logs.py` — CRUD, submit/approve/reject, role enforcement
- Use `httpx.AsyncClient` with `TestClient` + SQLite in-memory database (same pattern as Sprint 6)

---

## New Dependencies to Add to requirements-dev.txt

```
fastapi==0.115.x       # REST framework
uvicorn==0.32.x        # ASGI server (dev only)
httpx==0.28.x          # Async HTTP client for tests + TestClient
python-multipart==0.0.x  # File upload support (required by FastAPI)
python-jose[cryptography]==3.3.x  # JWT tokens
passlib[bcrypt]==1.7.x  # Password hashing
```

All free and open source.

---

## Constraints

- **No paid APIs**: All dependencies listed above are free/open source
- **Sprint 1-6 FROZEN**: FastAPI routers import from `extraction/`, `generation/`, `database/` — they do not modify Sprint 1-6 code
- **Teaching style**: Continue "Principal Engineer mentoring" approach — docstrings explaining WHY design choices were made

---

## Explicit Out of Scope for Sprint 7

- Frontend UI (Sprint 9)
- WhatsApp/email delivery of reports (Sprint 8)
- Real-time WebSocket status updates (Sprint 9)
- Celery + Redis task queue (Sprint 8)
- Multi-company admin UI (Sprint 10)
- Production Docker deployment (Sprint 10)
- Rate limiting, API keys for external clients (Sprint 10)
