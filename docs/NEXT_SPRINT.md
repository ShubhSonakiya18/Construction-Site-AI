# Next Sprint: Sprint 8 — Auth Hardening + Celery/Redis Task Queue

**Status:** AWAITING SPRINT 7 APPROVAL — Do not begin until Sprint 7 is approved.
**Prerequisites:** Sprint 7 APPROVED and FROZEN
**Supersedes:** Sprint 7 spec (now complete — see `app/` package and `docs/BACKEND_ARCHITECTURE.md`)

---

## Sprint 8 Goal

Harden the Sprint 7 backend for real multi-tenant, multi-user production use: real user provisioning (Sprint 7 shipped exactly one dev-only demo login), full role-based access control across all endpoints (Sprint 7 only enforces roles on the review-approval endpoints), and a real task queue (Sprint 7 used FastAPI `BackgroundTasks`, which does not survive a process restart and has no retry/observability).

---

## Deliverables

### 1. User Registration and Password Reset

- `POST /api/v1/auth/register` — create a new `User` row (with `hashed_password` set via `app.core.security.hash_password()`, the function Sprint 7 already built for the dev-admin bootstrap).
- `POST /api/v1/auth/forgot-password` / `POST /api/v1/auth/reset-password` — token-based reset flow (short-lived JWT or a dedicated `password_reset_tokens` table — decide during implementation; document the choice as a new ADR).
- Retire `app/core/dev_seed.py`'s role as "the only way to get a working login" — it can remain as a convenience for local development, but registration must not depend on it.

### 2. Full Role-Based Access Control

Sprint 7's `require_role()` dependency factory (`app/api/dependencies.py`) exists and is proven on `/daily-logs/{id}/approve` and `/reject`. Extend role enforcement to:
- `/audio/upload` — should any role be excluded from uploading? (e.g. `client` role should not upload foreman recordings)
- `/daily-logs/{id}/generate` — should generation be foreman-triggerable, or PM-only?
- `/projects/*` — read access should be scoped to users belonging to the project's `company_id` (Sprint 7's `CurrentUser.company_id` is already embedded in the JWT and available for this, but no route currently checks it against the resource being accessed — this is the actual multi-tenancy enforcement gap to close).

### 3. Celery + Redis Task Queue

Replace `app/services/pipeline_service.py`'s `BackgroundTasks` invocation with a real Celery task, per the extension point already documented in `docs/BACKEND_ARCHITECTURE.md` §10:

```python
# Sprint 7 (current):
background_tasks.add_task(run_pipeline, audio_file_id)

# Sprint 8 (target):
run_pipeline.delay(audio_file_id)
```

`run_pipeline`'s function body does not need to change — it was deliberately shaped in Sprint 7 (signature `(audio_file_id: UUID) -> None`, no shared request-scoped state, opens its own DB session) specifically so this migration is a decorator + a call-site change, not a rewrite. What Sprint 8 adds:
- Redis running locally (new infrastructure dependency — document setup in `docs/BACKEND_STARTUP.md`).
- `celery_app.py` — Celery application instance, configured with the Redis broker/backend.
- Retry policy for transient failures (Groq rate limits, Whisper OOM on a large file) — `run_pipeline` currently marks `AudioFile.processing_status = "failed"` on any stage failure with no retry; Celery's built-in retry mechanism should replace at least the "Groq unreachable" case.
- Task result backend so `GET /audio/{id}/status` could, if useful, also query Celery task state directly rather than only the `AudioFile.processing_status` column (evaluate whether this duplicates information usefully or not — document the decision).

### 4. Docker Compose for Local Development

Sprint 7 explicitly deferred Docker (see `docs/HANDOVER.md` note 7). Sprint 8 is a natural point to introduce a `docker-compose.yml` covering PostgreSQL + Redis + the FastAPI app, since Redis is now a required local dependency. Production-grade multi-stage Docker builds remain out of scope until Sprint 10 (per `docs/ROADMAP.md`).

### 5. Tests

- `tests/test_api_auth_registration.py` — registration success, duplicate email, weak password rejection.
- `tests/test_api_auth_password_reset.py` — full reset flow.
- `tests/test_api_rbac.py` — role enforcement across the newly-covered endpoints from Deliverable 2.
- `tests/test_pipeline_celery.py` — Celery task invocation, using Celery's `task_always_eager` test mode (no real Redis needed for CI, same "SQLite in-memory, no live infra" philosophy Sprint 6/7 established).

---

## Constraints

- **No paid APIs.** Redis is free/open-source and runs locally — no managed Redis service.
- **Sprint 1–7 FROZEN.** Extend `app/`, do not rewrite Sprint 7's routers/schemas/middleware unless fixing a verified bug (see `docs/CONTRIBUTING.md` §5 for the freeze-discipline pattern, already applied once when Sprint 7 hardened Sprint 6).
- **Maintain backward compatibility.** `POST /auth/login` must continue to work exactly as it does today (same request/response schema) — registration is additive, not a replacement of the login contract.
- **Continue the "explain, implement, test, verify" per-subsystem discipline** established in Sprint 7 — each of the 4 deliverables above should get its own design explanation, tests, and manual verification before moving to the next.

---

## Explicit Out of Scope for Sprint 8

- Frontend UI (Sprint 9)
- Real-time WebSocket status updates (Sprint 9)
- Multi-company admin UI (Sprint 10)
- Production Docker deployment / multi-stage builds (Sprint 10)
- Rate limiting, API keys for external clients (Sprint 10)
- Async repository layer (deferred indefinitely — see ADR-031 in `docs/DECISIONS.md`; revisit only if traffic actually demands it)
