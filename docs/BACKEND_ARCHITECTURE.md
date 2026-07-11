# Backend Architecture — Sprint 7

**Package:** `app/`
**Status:** COMPLETE — PENDING APPROVAL
**Prerequisites:** Sprints 1–6 (FROZEN)
**Companion doc:** `docs/BACKEND_STARTUP.md` (how to run it), `docs/CONTRIBUTING.md` (how to extend it)

This document explains the production FastAPI backend built in Sprint 7: why it is structured the way it is, how a request flows through it end to end, and the architectural decisions made along the way — including two decisions that deliberately keep `app/` and `database/` at arm's length from each other.

---

## 1. What Sprint 7 Is

Sprints 1–6 built a complete, working pipeline — audio in, structured data and four AI documents out — but every interface to it was a CLI script (`transcribe.py`, `extract.py`, `verify_sprint6.py`) or a Python import. Sprint 7 is the **first user-facing layer**: a REST API that exposes the same pipeline over HTTP, so a future frontend, mobile app, or third-party integration talks to `app/` and never touches `speech/`, `extraction/`, `generation/`, or `database/` directly.

Nothing in Sprints 1–6 was rewritten to make this possible. `app/` is purely an additive layer on top of frozen code — the one exception (`database/session.py` gaining `get_async_session()`) is additive within that file too; see §7.

---

## 2. Application Structure

```
app/
├── main.py                  ASGI entry point (uvicorn app.main:app)
├── create_app.py            Application factory — builds and wires everything
├── core/
│   ├── config.py            Settings (pydantic-settings) — the only os.environ reader in app/
│   ├── security.py          Password hashing (bcrypt) + JWT encode/decode
│   └── dev_seed.py          Dev-only demo login bootstrap (see §8)
├── api/
│   ├── dependencies.py      get_db, get_current_user, require_role, get_app_settings
│   └── v1/
│       ├── health.py        /health, /live, /ready, /version
│       ├── auth.py          /auth/login
│       ├── audio.py         /audio/upload, /audio/{id}/status
│       ├── daily_logs.py    /daily-logs/{id}, review lifecycle, /generate, /outputs
│       └── projects.py      /projects/{id}/daily-logs
├── services/
│   └── pipeline_service.py  Background-task orchestration: speech → extraction → DB → generation → DB
├── schemas/
│   ├── envelope.py          APIResponse[T] — the response shape every endpoint returns
│   ├── auth.py, daily_log.py, project.py, audio.py, generation.py
└── middleware/
    ├── request_id.py        Assigns/propagates X-Request-ID
    ├── logging.py            One structured log line per request
    ├── exception_handlers.py Exception → APIResponse mapping
    └── cors.py                CORS policy derived from Settings
```

Every router file maps 1:1 to a resource. Every schema file maps 1:1 to a router. This mirroring is deliberate — given a router, you always know where its request/response models live without searching.

---

## 3. Request Lifecycle

A request to a protected endpoint (e.g. `GET /api/v1/daily-logs/{id}`) flows through:

```
Client
  │  HTTP request, Authorization: Bearer <jwt>
  ▼
RequestIDMiddleware        assigns/reuses X-Request-ID, stores in a ContextVar
  ▼
LoggingMiddleware          starts a timer
  ▼
CORSMiddleware              (Starlette built-in — origin check)
  ▼
GZipMiddleware               (Starlette built-in — response compression)
  ▼
Router dispatch              FastAPI matches path + method to app/api/v1/daily_logs.py
  ▼
Dependency injection         Depends(get_db)          → sync Session, opened in a threadpool
                              Depends(get_current_user) → decodes JWT, returns CurrentUser
  ▼
Route handler                 app/api/v1/daily_logs.py:get_daily_log()
  ▼
Repository layer              DailyLogRepository(session).get_with_children(log_id)
  ▼
Database                      PostgreSQL (or SQLite in-memory under test)
  ▼
Repository layer               returns ORM DailyLog + all child collections
  ▼
Route handler                  DailyLogRead.model_validate(orm_object)
  ▼
Response model                 success_response(data) → APIResponse[DailyLogRead]
  ▼
(if an exception was raised at any point above: an exception handler in
 app/middleware/exception_handlers.py builds an APIResponse instead —
 see §6)
  ▼
LoggingMiddleware              logs request_id, method, path, status, duration_ms
  ▼
RequestIDMiddleware             writes X-Request-ID onto the response headers
  ▼
Client
  receives: {success, message, data, metadata, errors, timestamp, request_id}
```

Every stage's responsibility:

| Stage | Responsibility |
|---|---|
| RequestIDMiddleware | Correlate one request across all log lines and the client-visible header. |
| LoggingMiddleware | One line per request; never logs bodies, headers, or secrets. |
| CORS/GZip | Cross-origin policy, response compression — Starlette built-ins, no custom code. |
| Dependencies | Supply a DB session and/or an authenticated principal — routers never construct either themselves. |
| Route handler | Translate HTTP concerns (path params, query params, status codes) into a repository/service call and back. Contains no business logic of its own beyond that translation. |
| Repository | All SQL. The only layer that imports SQLAlchemy. |
| Schema | Validates/serializes the boundary between ORM objects and JSON. |
| Exception handlers | Guarantee every response — success or failure — has the same envelope shape. |

---

## 4. Dependency Injection

Two dependencies matter to almost every route:

- **`get_db()`** (`app/api/dependencies.py`) — yields a `sqlalchemy.orm.Session`, opened via the existing Sprint 6 `database.session.get_session()`/`get_engine()`. Declared as a plain `def` generator (not `async def`), which FastAPI runs in a worker threadpool automatically — routers stay non-blocking without the repository layer needing to be async (see §7 for why that matters).
- **`get_current_user()`** — decodes the `Authorization: Bearer <jwt>` header via `app.core.security.decode_access_token()`, returning a `CurrentUser(user_id, company_id, role, email)` dataclass built entirely from JWT claims (no extra DB round-trip per request). Raises `HTTPException(401)` for a missing, malformed, expired, or wrong-signature token.
- **`require_role(*roles)`** — a dependency *factory* built on top of `get_current_user()`. `Depends(require_role("owner", "project_manager"))` raises `403` if the caller's role isn't in the allow-list. Used on `/daily-logs/{id}/approve` and `/reject`.
- **`get_app_settings()`** — returns `request.app.state.settings`, **not** the module-level cached `app.core.config.get_settings()`. This distinction is load-bearing — see the sidebar below.

> **Why `get_app_settings()` reads `request.app.state`, not the `get_settings()` singleton**
> `create_app(settings=...)` accepts an explicit `Settings` override specifically so tests can build an isolated app with a known JWT secret (`tests/conftest_api.py`). Early in this sprint, `app/api/v1/auth.py` and `app/api/v1/health.py` depended on `get_settings()` directly — the process-wide `lru_cache`-d singleton — which silently ignored that override. The bug was invisible until the test suite caught it: `test_token_contains_expected_claims` failed because login had signed the JWT with the *real* `.env` secret while the test tried to verify it against the test app's distinct secret; `test_returns_version_metadata` failed because `/version` reported `environment=development` instead of the test app's `testing`. Every route that needs `Settings` now depends on `get_app_settings()` instead. This is the kind of bug that only a real request through the real app factory — not an isolated unit test — will surface, which is why §9 below insists on running the actual server, not only `TestClient`.

---

## 5. API Versioning Strategy

Every router is mounted under `/api/v1` in `create_app.py`:

```python
app.include_router(health_router.router, prefix="/api/v1")
app.include_router(auth_router.router, prefix="/api/v1")
...
```

`app/api/v1/` is a self-contained package: its routers, and the schemas in `app/schemas/` they use, belong to version 1 of the contract. A future `/api/v2` is a **sibling package**, `app/api/v2/`, with its own routers and (if the shape genuinely changed) its own schemas — never a modification to `v1/`'s files. Two consequences of this design:

- A v1 client's contract never breaks because v2 was added. `v1/daily_logs.py` is not touched when `v2/daily_logs.py` is created.
- Version-specific behavior lives *only* in the version's router layer. `app/services/pipeline_service.py` and every `database/repositories/*.py` call are version-agnostic — v2 routers would call the exact same service functions and repositories that v1 does, just wrap the result in a v2-shaped schema if the response contract changed.

If v2 needs a genuinely different service-layer behavior (not just a different response shape), that becomes a new function in `app/services/`, not a fork of an existing one — see `docs/CONTRIBUTING.md` "How to add a new API endpoint."

---

## 6. Error Handling & The Response Envelope

Every response — success or failure — has the same top-level shape (`app/schemas/envelope.py`):

```json
{
  "success": true,
  "message": "Daily log retrieved.",
  "data": { "...": "..." },
  "metadata": null,
  "errors": null,
  "timestamp": "2026-07-11T00:00:00Z",
  "request_id": "a1b2c3d4-..."
}
```

`app/middleware/exception_handlers.py` registers five handlers on the FastAPI app (`app.add_exception_handler`, not a `BaseHTTPMiddleware` — see the module docstring for why exception handlers are the correct FastAPI mechanism here, not another middleware layer):

| Exception | HTTP Status | Source |
|---|---|---|
| `RequestValidationError` | 422 | Pydantic body/query/path validation failure |
| `HTTPException` | whatever the raiser specified | Explicit `raise HTTPException(...)` in a route or dependency (401, 403, 404, 400, 413, ...) |
| `ValueError` | 409 Conflict | Repository business-rule violations — e.g. `DailyLogRepository.approve()` called on a log that isn't `under_review`/`draft` |
| `TypeError` | 500 | Programming error (e.g. calling `soft_delete()` on a model without `SoftDeleteMixin`) |
| `Exception` (catch-all) | 500 | Anything unexpected — logged server-side with a full traceback via `logger.exception()`, but the client only ever sees a generic message. No stack trace, exception type, or internal file path is ever returned to the client. |

The `ValueError → 409` mapping is what makes `app/api/v1/daily_logs.py`'s review-lifecycle endpoints so thin: the state-machine logic (`draft → under_review → approved | rejected`) lives entirely in `DailyLogRepository` (Sprint 6, frozen), and the router does not duplicate it — it just calls the repository method and lets an illegal transition surface as `ValueError`, which the global handler turns into a `409` automatically.

---

## 7. Why the Repository Layer Stays Sync-Only

Sprint 7 added `database.session.get_async_session()` (an `AsyncSession` backed by `asyncpg`) alongside the existing sync `get_session()`. It would be natural to assume FastAPI routes should use it — but they don't, and this section explains why.

**The problem:** `database/repositories/base.py` and every repository built on it call `self._session.execute(stmt)`, `.get()`, `.flush()`, `.delete()` — all *synchronous* calls. `AsyncSession`'s equivalent methods are coroutines; calling them without `await` does not raise an error, it silently returns an unawaited coroutine object instead of a result. Handing an `AsyncSession` to `DailyLogRepository` would not fail loudly — it would fail by returning garbage.

**The decision:** keep `database/repositories/` synchronous, and route handlers use the sync `get_session()` via `app/api/dependencies.py:get_db()`. FastAPI runs `def` (non-`async def`) dependency generators in a worker threadpool automatically, so this does **not** block the event loop — a sync repository call inside an async route handler behaves correctly, just not with the theoretical maximum concurrency an all-async stack would offer.

**Why not rewrite the repositories as async** (the alternative considered): it would mean either (a) maintaining two parallel repository trees — `AsyncBaseRepository` plus an async version of all 12 repository classes — doubling the surface area and the risk of the two drifting out of sync, or (b) rewriting the single sync tree in place, which breaks every Sprint 1–6 CLI tool (`transcribe.py`, `extract.py`, `verify_sprint6.py`, all `tests/test_db_*.py`) that calls these repositories synchronously today. Neither is proportionate to the problem: this project's target scale (per `docs/DECISIONS.md` multi-tenancy notes — hundreds of companies, not tens of thousands) does not need async DB access to meet its performance requirements; the threadpool-offload approach is sufficient.

**What `get_async_session()` is actually for, given this constraint:** direct SQLAlchemy Core usage from async code that does not go through the repository layer — e.g., a future lightweight `SELECT 1` health check or hand-written async queries. It is documented in `database/session.py`'s module docstring as explicitly NOT for repository use.

**Migration strategy, if repositories ever need to become async:** the `BaseRepository[T]` generic interface (`get_by_id`, `list`, `create`, `update`, `soft_delete`, `restore`, `hard_delete`) is small and uniform by design — every subclass follows the same shape. If a future sprint's traffic profile genuinely requires async DB access at the repository layer (not just at the route layer, which is already effectively non-blocking via the threadpool), the migration path is:
1. Add `AsyncBaseRepository[T]` with `async def` equivalents of the same method names.
2. Migrate one repository at a time, starting with the highest-traffic one (`DailyLogRepository`), keeping the sync version until all call sites (CLI scripts included) have been ported.
3. Because every repository method signature is already narrow and consistent, an async rewrite is mechanical — `await self._session.execute(stmt)` instead of `self._session.execute(stmt)` — not a redesign.

This is a deferred decision, not a limitation baked into the schema or the repository *interface* — only into today's *implementation*.

---

## 8. Why `database/` Has No Dependency on `app/`

Sprint 7 needed exactly one authenticated demo account (`admin@example.com` / `Admin@123`) so `POST /api/v1/auth/login` has something real to authenticate against. The naive approach — hash the password directly inside `database/seed/sample_data.py` — was rejected.

**The problem with hashing in `database/seed/`:** `database/` is Sprint 6, frozen, and deliberately framework-independent — usable from a CLI tool, a future non-FastAPI consumer, a data-migration script, or Alembic itself, without dragging in `app/`'s dependencies (`passlib`, `python-jose`, `pydantic-settings`, eventually FastAPI itself). Importing `app.core.security.hash_password()` from `database/seed/sample_data.py` would invert the dependency direction: the lower, more-reusable layer (`database/`) would depend on the higher, more-specific layer (`app/`). That makes `database/` harder to reuse (anything importing `database.seed` now transitively needs `app/`'s dependencies installed) and harder to test in isolation.

**The resolution:**
- `database/seed/sample_data.py` seeds a placeholder `User` row (`DEV_ADMIN_ID`) with `hashed_password=None` — no password logic, no dependency on `app/`.
- `app/core/dev_seed.py` is the one place in this codebase where the application layer reaches back into already-seeded data: `ensure_dev_admin_password()` looks up that same row (by its known fixed UUID) and sets the hash, using `app.core.security.hash_password()` — code that is entirely appropriate to live in `app/`, since it *is* the application layer.
- `bootstrap_dev_environment()` chains the existing Sprint 6 seed calls (`seed_all_reference_data`, `seed_sample_data`) with `ensure_dev_admin_password()`, giving a single command (`python -m app.core.dev_seed`) that does the same job the naive approach would have, but with the dependency arrow pointing the correct direction: `app/ → database/`, never the reverse.

This was verified directly: `grep -rn "^from app\|^import app" database/` returns zero matches.

---

## 9. Manual Verification Discipline

This sprint's build process ran the actual server twice — once via `fastapi.testclient.TestClient` (in-process, fast, used for the automated test suite) and once via a real `uvicorn app.main:app` process bound to a real socket, hit with `curl`. The second pass caught a bug the first did not: `TestClient`-based smoke tests had `.env` already loaded into `os.environ` by the calling script, masking the fact that `app/main.py` itself never loaded it. A genuine `uvicorn` launch from a clean shell failed with `RuntimeError: DATABASE_URL environment variable is not set` until `load_dotenv()` was added to `app/main.py` (see that file's docstring for the full explanation, including why `pydantic-settings`' own `.env` parsing inside `Settings` does not solve this — it populates the `Settings` object's fields, not `os.environ` itself, and `DatabaseConfig`/`ExtractionConfig`/`GenerationConfig`/`SpeechProcessingConfig` all read raw `os.environ`).

The lesson generalizes: **`TestClient` alone is not sufficient manual verification for a change that touches process startup, environment loading, or anything that behaves differently between "imported into a test runner that already configured its environment" and "launched fresh."** `docs/BACKEND_STARTUP.md` documents the real startup sequence this verification pass confirmed works.

---

## 10. Background Task Readiness (Sprint 8 Extension Point)

Sprint 7 explicitly does not implement Celery — `app/services/pipeline_service.py:run_pipeline()` runs as a FastAPI `BackgroundTasks` job, queued from `app/api/v1/audio.py:upload_audio()`:

```python
background_tasks.add_task(run_pipeline, audio_file_id)
```

`run_pipeline` was deliberately shaped so this line is the *only* thing that changes when Celery arrives:

- **Signature:** `run_pipeline(audio_file_id: UUID) -> None`. No `Request`, no `Session`, no other live object — everything it needs, it re-fetches from the database using the id it was given. This is exactly the signature a Celery task needs too.
- **No shared state:** it opens its own `get_session()` calls, exactly like a Sprint 1–6 CLI script would, rather than reusing anything from the request that triggered it (which will already have completed and returned a response by the time this function runs).
- **Structured failure, not exceptions:** every stage (`SpeechProcessingPipeline.process()`, `ExtractionPipeline.extract()`, `AIServiceManager.generate_all()`) already returns a `.success`/`.errors` result object rather than raising for expected failure modes (a Sprint 1–6 convention, not something introduced here) — `run_pipeline` checks `.success` at each stage and marks `AudioFile.processing_status = "failed"` with the captured error, rather than letting an exception escape into `BackgroundTasks`' internal handling (which only logs it — the client has no way to ever see it except by polling).

**Sprint 8's migration**, when it happens: `run_pipeline` gets decorated with `@celery_app.task`, and `audio.py` changes `background_tasks.add_task(run_pipeline, audio_file_id)` to `run_pipeline.delay(audio_file_id)`. `pipeline_service.py`'s body does not change.

The same shape applies to any other multi-step Sprint 1–6 orchestration that later needs to move off the request/response cycle — `app/api/v1/daily_logs.py:trigger_generation()` currently runs synchronously (documented in its own docstring as an intentional choice: single-log generation is fast enough not to need backgrounding), but if that assumption stops holding, extracting it into `app/services/generation_service.py` with the same `(id) -> None` shape is the same mechanical move.

---

## 11. What Sprint 7 Does Not Include

Per `docs/NEXT_SPRINT.md` and explicit scope decisions made during this sprint:

- **No user registration or password reset.** Exactly one seeded demo account exists (`app/core/dev_seed.py`). Sprint 8 defines real user provisioning.
- **No Celery/Redis task queue.** FastAPI `BackgroundTasks` only — see §10.
- **No frontend.** Sprint 9.
- **No async repositories.** See §7.
- **No `/api/v2`.** The versioning structure (§5) supports adding one without touching `v1/`, but v2 itself does not exist yet.
