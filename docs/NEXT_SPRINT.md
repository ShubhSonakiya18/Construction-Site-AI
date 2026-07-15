# Next Sprint: Sprint 9 — Task Queue, Email Delivery, and Frontend Core

**Status:** AWAITING SPRINT 8 APPROVAL — Do not begin until Sprint 8 is approved.
**Prerequisites:** Sprint 8 APPROVED and FROZEN
**Supersedes:** The original Sprint 8 spec (Celery/Redis + registration) — that spec was superseded mid-sprint by an expanded scope (RBAC, multi-tenancy, user management, security hardening, audit logging). This document reflects what was actually deferred out of Sprint 8, not what Sprint 8 originally planned.

---

## Sprint 9 Goal

Close the gaps Sprint 8 deliberately deferred: replace `BackgroundTasks` with a real task queue (Celery + Redis), wire up real email delivery for the Sprint 8 password-reset flow, and begin the React frontend. These three are independent enough that they could also be split across separate sprints if preferred — flagged as a decision point below.

---

## Deliverables

### 1. Celery + Redis Task Queue

Replace `app/services/pipeline_service.py`'s `BackgroundTasks` invocation with a real Celery task, per the extension point documented in `docs/BACKEND_ARCHITECTURE.md` §10:

```python
# Current:
background_tasks.add_task(run_pipeline, audio_file_id)

# Target:
run_pipeline.delay(audio_file_id)
```

`run_pipeline`'s function body does not need to change — it was deliberately shaped (signature `(audio_file_id: UUID) -> None`, no shared request-scoped state, opens its own DB session) specifically so this migration is a decorator + a call-site change, not a rewrite.

What Sprint 9 adds:
- Redis running locally (new infrastructure dependency — document setup in `docs/BACKEND_STARTUP.md`).
- `celery_app.py` — Celery application instance, Redis broker/backend.
- Retry policy for transient failures (Groq rate limits, Whisper OOM) — `run_pipeline` currently marks `AudioFile.processing_status = "failed"` with no retry.
- **Also consider:** migrating `MemoryRateLimiter` (Sprint 8, `app/core/rate_limit.py`) to `RedisRateLimiter` in the same sprint, since Redis becomes available anyway — the `RateLimiter` Protocol was designed for exactly this swap (ADR-041). Zero router/service changes required; only the constructed instance changes.

### 2. Real Email Delivery for Password Reset

Sprint 8 built the full password-reset **token lifecycle** (`docs/AUTHENTICATION_ARCHITECTURE.md` §4) but explicitly deferred actual email delivery — in development/testing, the raw reset token is returned directly in the API response for manual verification; in production, `AuthService.forgot_password()` returns `None` and nothing is sent anywhere.

- Choose a free/open-source email delivery mechanism (SMTP via a free-tier provider, or a local SMTP relay for self-hosted deployments — no paid SaaS, consistent with the project's "no paid services" constraint).
- Wire it into `AuthService.forgot_password()` at the point currently marked "the placeholder for the future email step."
- Remove the dev-mode raw-token response once delivery is real (or keep it behind an explicit dev-only flag for local testing without a mail server).

### 3. Row-Level Security (Optional Defense-in-Depth)

Sprint 8 resolved application-layer tenant scoping (`TenantScopedRepository`, ADR-037) as sufficient for the current threat model. PostgreSQL Row-Level Security remains an **open, optional** future decision — revisit only if a second layer of defense is judged necessary (e.g. before a compliance audit), not as a required Sprint 9 deliverable.

### 4. React Frontend Core (if scoped into this sprint)

- Login/logout flow (consuming Sprint 8's `/auth/login`, `/auth/refresh`, `/auth/logout`)
- Dashboard (active projects, recent logs)
- Voice recording interface
- Log review interface (approve/reject, using Sprint 8's RBAC-gated endpoints)
- Responsive design (mobile-first)

**Decision point:** Deliverables 1–2 (task queue, email) are backend infrastructure; Deliverable 4 is a new frontend package. These may be better split into two sprints (Sprint 9: task queue + email; Sprint 10: frontend) rather than combined — confirm scope before starting.

### 5. Tests

- `tests/test_pipeline_celery.py` — Celery task invocation via `task_always_eager` (no real Redis needed for CI).
- `tests/test_redis_rate_limiter.py` — if the `RedisRateLimiter` migration is included.
- `tests/test_email_delivery.py` — mocked SMTP, verifying `forgot_password()` triggers a send in production mode.
- Frontend: component tests per whatever framework is chosen (Jest/Vitest + Testing Library, typical for React).

---

## Constraints

- **No paid APIs, no paid SaaS.** Redis is free/open-source and runs locally. Email delivery must use a free-tier or self-hosted option.
- **Sprint 1–8 FROZEN.** Extend `app/`/`database/`, do not rewrite Sprint 8's services/routers/schemas unless fixing a verified bug (see `docs/CONTRIBUTING.md` §5 for the freeze-discipline pattern, applied consistently across Sprints 7 and 8).
- **Maintain backward compatibility.** Every Sprint 1–8 endpoint's request/response contract must continue to work unchanged.
- **Continue the "explain, implement, test, verify" per-subsystem discipline** established in Sprints 7–8.

---

## Explicit Out of Scope for Sprint 9

- Multi-company admin UI (Sprint 10+)
- Production Docker deployment / multi-stage builds (Sprint 10+)
- API keys for external clients (Sprint 10+)
- Async repository layer (deferred indefinitely — see ADR-031; revisit only if traffic demands it)
- Mandatory Row-Level Security (optional, see Deliverable 3 above)
