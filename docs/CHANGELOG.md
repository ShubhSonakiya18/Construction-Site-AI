# CHANGELOG

All notable changes to Construction Site AI are documented here.
Format: `[Sprint X] Date — Description`

---

## [Sprint 8] 2026-07-15 — Authentication, Authorization & Multi-Tenant Hardening

### Added

#### Subsystem 1 — Authentication Core
- `database/models/auth.py` — `UserSession` (server-side refresh-token store, hash-only, rotation on every refresh)
- `database/models/password_reset.py` — `PasswordResetToken` (single-use, short-lived, hash-only)
- `database/repositories/auth.py`, `database/repositories/password_reset.py`
- `database/migrations/versions/002_user_sessions.py`
- `app/services/auth_service.py` — `AuthService`: login, refresh, logout, logout-all, change-password, forgot-password, reset-password
- New endpoints: `POST /auth/refresh`, `/logout`, `/logout-all`, `/change-password`, `/forgot-password`, `/reset-password`, `GET /auth/me`
- `POST /auth/login` response extended additively (`refresh_token`, `refresh_token_expires_in_days`, `session_id`)

#### Subsystem 2 — RBAC & Permission System
- `app/core/permissions.py` — `Permission` enum (25 permissions), `ROLE_PERMISSIONS` mapping all 6 existing roles + new `system_admin`
- `require_permission()` dependency, replacing hardcoded `require_role()` lists — wired into all 9 daily-log/audio/project endpoints (7 of which had no authorization check at all before this)

#### Subsystem 3 — Multi-Tenancy Scoping
- `database/repositories/tenant.py` — `TenantContext`, `TenantScopedRepository` base class
- `*_scoped()` and `*_cross_tenant()` methods on `DailyLogRepository`, `ProjectRepository`, `AudioRepository`
- `system_admin` cross-tenant bypass: explicit methods only, mandatorily audited
- All company-owned resource routes now return 404 (not silent success) for cross-tenant access attempts

#### Subsystem 4 — User Management
- `app/services/user_service.py` — `UserService`: create, profile update, deactivate/restore, role assignment
- `app/api/v1/users.py` — 8 endpoints: create, list, get, update-profile, deactivate, restore, assign-role, unlock
- Role assignment hierarchy (`ROLE_RANK`, `can_assign_role()`): no self-assignment, no assigning above own rank, last-owner/admin protection

#### Subsystem 5 — Security Hardening
- `app/core/rate_limit.py` — `RateLimiter` Protocol + `MemoryRateLimiter` (Redis-swappable, see ADR-041)
- `app/middleware/security_headers.py` — `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, production-only HSTS
- `database/migrations/versions/003_account_lockout.py` — `failed_login_attempts`, `locked_until`, `last_failed_login_at` on `User`
- Account lockout (5 attempts / 15 min, configurable), rate limiting on login (10/5min) and forgot-password (3/hour)
- `POST /users/{id}/unlock` — admin unlock endpoint

#### Subsystem 6 — Audit Logging
- `database/migrations/versions/004_audit_log_structured_fields.py` — `target_user_id`, `ip_address`, `user_agent`, `request_id`, `success` added to `AuditLog` as first-class indexed columns
- `app/services/audit_helpers.py` — `safe_log_event()` fail-open wrapper
- 20+ audit event types across authentication, lockout, user management, and security (unauthorized/forbidden access, rate-limit triggers)

#### Documentation
- `docs/AUTHENTICATION_ARCHITECTURE.md`, `docs/AUTHORIZATION_ARCHITECTURE.md` — new
- ADR-035 through ADR-041 (see `docs/DECISIONS.md`)

### Tests
- 121 new tests across 5 new test files (`test_api_auth_sprint8.py` +24, `test_api_rbac.py` +8, `test_core_permissions.py` +12, `test_multi_tenant_isolation.py` +15, `test_api_users.py` +19, `test_api_security_hardening.py` +13, `test_audit_logging.py` +21, plus 1 updated Sprint 7 test for the intentional 404-not-200 behavior change)
- Full suite: 913 passed, 1 skipped, 0 regressions (up from Sprint 7's 801)
- Live-verified against real PostgreSQL for every subsystem

### Fixed
- **Account lockout never persisted** — `AuthService._record_failed_login()`'s state change was rolled back by the request-scoped session's `except Exception: rollback()` handler, because it ran immediately before the route's intentional `401` raise. Fixed by committing that specific state change immediately. See ADR-040 and "Known Bugs Found and Fixed — Sprint 8" in `docs/DECISIONS.md`.
- **Audit events for security rejections were silently discarded** — same root cause as above, affecting `security.unauthorized_access`, `security.forbidden_access`, lockout, and rate-limit events. Fixed by making `safe_log_event()` commit immediately on success.
- **`UserRead` schema had `id`/`company_id` typed as `str` instead of `UUID`** — caused every user create/read response to fail Pydantic validation, surfacing as a misleading `409`. Fixed to match every other `*Read` schema in the codebase.

### Architecture Decisions (see `docs/DECISIONS.md` for full write-ups)
- Opaque, server-backed refresh tokens (not stateless JWTs) — ADR-035
- Extend existing 6 roles + add `system_admin` only; RBAC as a permission layer — ADR-036
- Tenant scoping enforced at the repository layer, not the router layer — ADR-037
- 404 (not 403) for cross-tenant access attempts — ADR-038
- `AuditLog` extended with first-class structured columns, JSON metadata retained — ADR-039
- Fail-open audit logging, with the cross-tenant-access event as the sole exception — ADR-040
- `RateLimiter` as a swappable Protocol, in-memory for Sprint 8 — ADR-041

---

## [Sprint 7] 2026-07-11 — Production FastAPI Backend

### Added

#### Application Core
- `app/main.py` — ASGI entry point. Calls `load_dotenv()` before importing anything else, so `DatabaseConfig.from_env()` and friends (which read raw `os.environ`, not `pydantic-settings`) see `.env` values under a real `uvicorn` launch the same way they already do under every Sprint 1-6 CLI script.
- `app/create_app.py` — Application factory (`create_app(settings=None)`), not a module-level `app = FastAPI()`, so tests can build an isolated app instance with explicit `Settings` overrides. Lifespan context manager refuses to start in production with the default JWT secret or an open (`*`) CORS policy.
- `app/core/config.py` — `Settings` (pydantic-settings `BaseSettings`), the sole `os.environ` reader inside `app/`. Delegates to the existing `DatabaseConfig`/`ExtractionConfig`/`GenerationConfig`/`SpeechProcessingConfig.from_env()` classes via factory methods rather than redeclaring `DATABASE_URL`/`GROQ_API_KEY`/etc. as new fields — avoids two independent readers of the same env var drifting out of sync.
- `app/core/security.py` — `hash_password()`/`verify_password()` (bcrypt via passlib), `create_access_token()`/`decode_access_token()` (JWT via python-jose). Pure functions, no FastAPI/DB dependency.
- `app/core/dev_seed.py` — Dev-only demo login bootstrap (`admin@example.com` / `Admin@123`, overridable via `.env`). Sets the password hash on a placeholder `User` row that `database/seed/sample_data.py` seeds with `hashed_password=None` — keeps `database/` free of any dependency on `app/` (see ADR below and `docs/BACKEND_ARCHITECTURE.md` §8).

#### API Layer (`/api/v1`)
- `app/api/v1/health.py` — 4 distinct health endpoints: `/health` (full diagnostic — real DB + Groq check), `/live` (no I/O, Kubernetes livenessProbe), `/ready` (DB check, Kubernetes readinessProbe), `/version` (static build metadata).
- `app/api/v1/auth.py` — `POST /auth/login`. Sprint 7 scope only: no registration, no password reset (per `docs/NEXT_SPRINT.md` §3).
- `app/api/v1/audio.py` — `POST /audio/upload` (saves file, queues background pipeline via `BackgroundTasks`), `GET /audio/{id}/status` (polling).
- `app/api/v1/daily_logs.py` — `GET /daily-logs/{id}`, review lifecycle (`/submit`, `/approve`, `/reject` — delegates entirely to the frozen `DailyLogRepository` state machine), `/generate` (re-run AI documents), `/outputs`.
- `app/api/v1/projects.py` — `GET /projects/{id}/daily-logs` with pagination metadata.
- `app/api/dependencies.py` — `get_db` (sync `Session`, threadpool-offloaded by FastAPI automatically), `get_current_user` (JWT decode → `CurrentUser`), `require_role(*roles)` (403 for insufficient role), `get_app_settings` (reads `request.app.state.settings`, **not** the process-wide `get_settings()` singleton — see Fixed section).

#### Service Layer
- `app/services/pipeline_service.py` — `run_pipeline(audio_file_id)`, the full orchestration chain: `SpeechProcessingPipeline.process()` → `ExtractionPipeline.extract()` → `DailyLogRepository.create_from_extraction_result()` → `AIServiceManager.generate_all()` → `GenerationRepository.create_from_service_output()`. Runs as a `BackgroundTasks` job; shaped so the eventual Celery migration (Sprint 8) is a one-line call-site change, not a rewrite of this function.

#### Schemas & Response Envelope
- `app/schemas/envelope.py` — `APIResponse[T]` generic envelope (`success`, `message`, `data`, `metadata`, `errors`, `timestamp`, `request_id`) returned by every endpoint, success or error. `request_id` sourced from a `ContextVar`, not threaded through every function call.
- `app/schemas/{auth,daily_log,project,audio,generation}.py` — Pydantic request/response models, kept deliberately separate from `database/models/` (ORM) so an internal schema change doesn't silently break the public API contract.

#### Middleware
- `app/middleware/request_id.py` — `RequestIDMiddleware`, assigns/reuses `X-Request-ID`, exposes it via a `ContextVar` so `success_response()`/`error_response()` can read it from anywhere.
- `app/middleware/logging.py` — `LoggingMiddleware`, one structured line per request. Never logs bodies, headers, or secrets.
- `app/middleware/exception_handlers.py` — 5 handlers mapping `RequestValidationError`→422, `HTTPException`→as-raised, `ValueError`→409 (repository business-rule violations), `TypeError`→500, catch-all `Exception`→500 (full traceback logged server-side, never returned to the client).
- `app/middleware/cors.py` — CORS policy derived from `Settings`, with the credentialed-`*`-origin CORS-spec trap documented and avoided.

#### Database — Additive Only
- `database/session.py` — `get_async_engine()`/`get_async_session()`/`reset_async_engine()` added alongside the existing sync `get_engine()`/`get_session()`. For direct SQLAlchemy Core usage from async code only — **not** for `database/repositories/`, which stay synchronous (every repository method calls `session.execute()`/`.get()`/`.flush()` without `await`; handing them an `AsyncSession` would silently return unawaited coroutines instead of results). Full rationale and future migration path in `docs/BACKEND_ARCHITECTURE.md` §7.
- `database/seed/sample_data.py` — Added a placeholder `DEV_ADMIN_ID` `User` row (`hashed_password=None`) for the Sprint 7 demo login. No new dependency on `app/` — the hash is set afterward by `app.core.dev_seed`.

#### Tests
- `tests/test_api_health.py`, `test_api_auth.py`, `test_api_daily_logs.py`, `test_api_audio.py` — 31 tests, all using `tests/conftest_api.py`'s isolated in-memory-SQLite `api_client` fixture (`create_app(settings=test_settings)` + `dependency_overrides[get_db]`). No live PostgreSQL required for CI.
- `tests/test_db_async_session.py` — 12 tests for the new async session machinery.
- `tests/test_core_security.py` — 12 tests for password hashing and JWT encode/decode.
- `tests/test_app_dev_seed.py` — 4 tests for the dev-admin bootstrap.
- `pytest.ini` — new file, `asyncio_mode = auto` (required for `async def test_...` in the async-session and future async tests).

### Fixed

- **`Depends(get_settings)` bypassing `create_app(settings=...)` overrides.** `app/api/v1/auth.py` and `app/api/v1/health.py` originally depended on the module-level cached `app.core.config.get_settings()` singleton, which ignores whatever `Settings` a specific app instance was built with. This broke JWT signing/verification and the `/version` endpoint under any non-default settings — caught by `tests/test_api_auth.py::test_token_contains_expected_claims` and `tests/test_api_health.py::test_returns_version_metadata` failing. Fixed by introducing `get_app_settings()` (reads `request.app.state.settings`) and switching every route that needs `Settings` to depend on it instead.
- **`.env` not loaded under a real `uvicorn` launch.** `app/main.py` originally did not load `.env` at all — `DatabaseConfig.from_env()` and the other Sprint 1-6 `*Config.from_env()` classes read raw `os.environ`, which a bare `uvicorn app.main:app` invocation never populates from `.env` (unlike `python extract.py`, which hand-rolls its own `_load_env()`). Caught only by launching a real server process and hitting it with `curl` — `TestClient`-based tests had `.env` already loaded into `os.environ` by the calling script, masking the gap. Fixed with `load_dotenv()` at the top of `app/main.py`.

### Dependencies Added (`requirements-dev.txt`)

```
pytest-asyncio==0.24.0
fastapi==0.115.6
uvicorn[standard]==0.32.1
httpx==0.28.1                (already present transitively via groq; now explicit)
python-multipart==0.0.20
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
bcrypt==4.0.1                 PINNED — passlib 1.7.4 (unmaintained since 2020) crashes
                              against bcrypt>=4.1 (AttributeError on bcrypt.__about__,
                              then a 72-byte ValueError on every hash/verify call)
pydantic-settings==2.7.1
python-dotenv==1.2.2
email-validator==2.2.0        required by pydantic.EmailStr
aiosqlite==0.20.0             async SQLite driver, tests only
asyncpg==0.30.0                already listed since Sprint 6 but was not actually
                              installed in the venv; installed for real this sprint
```

### Architecture Decisions (see `docs/BACKEND_ARCHITECTURE.md` for full write-ups)

- Repository layer stays synchronous; FastAPI routes use the sync `get_session()` via a threadpool-offloaded dependency rather than rewriting 12 repository classes as async.
- `database/` has zero dependency on `app/` — the dev-admin password hash is set by application-layer code reaching back into already-seeded data, not by the seed script importing `app.core.security`.
- `/api/v1` prefix with `app/api/v1/` as a self-contained package — a future `/api/v2` is a sibling package, never a modification to `v1/`.

---

## [Sprint 5.1] 2026-07-08 — Hardening & Optimization Pass

### Added

#### Prompt Cache Improvements
- `generation/prompts/loader.py` — `PromptLoader` now tracks `_mtime: dict[str, float]`; every `.load()` call compares the current `os.path.getmtime()` against the stored mtime and automatically evicts and reloads changed files. Prompt engineers can edit `.md` files with no process restart required.

#### Prompt Registry
- `generation/prompts/registry.py` — New `PromptRegistry` + `PromptRegistration`; `DEFAULT_PROMPT_REGISTRY` pre-registers all 4 built-in prompts with name, description, `expected_output`, service class name, and required variables. `validate()` detects unknown prompt names early.

#### Service Registry
- `generation/services/registry.py` — New `ServiceRegistry` + `ServiceRegistration`; `DEFAULT_SERVICE_REGISTRY` pre-registers all 4 built-in services. `create_all()` instantiates services with shared dependencies. Adding a new service = create class + call `register()`. Zero `AIServiceManager` changes.
- `generation/manager.py` — `AIServiceManager.__init__()` refactored to call `registry.create_all()`. New `service_registry=` parameter for partial-registry DI in tests.

#### Generation ID
- `generation/models/outputs.py` — `ServiceMetadata` gains `generation_id: str` (UUID4, auto-assigned). Correlation key linking logger lines, events, and results. Fully backward-compatible — existing tests unaffected.

#### Observability Layer
- `generation/observability/__init__.py` — Public API: `METRICS`, `GenerationMetrics`, `Timer`
- `generation/observability/events.py` — 9 typed frozen event dataclasses: `GenerationStartedEvent`, `GenerationCompletedEvent`, `GenerationFailedEvent`, `RetryStartedEvent`, `RetryCompletedEvent`, `ValidationFailedEvent`, `PromptCacheHitEvent`, `PromptCacheMissEvent`
- `generation/observability/timers.py` — `Timer` context manager (`time.monotonic()`; `elapsed`, `is_running`, explicit `start()`/`stop()`, `__enter__`/`__exit__`)
- `generation/observability/metrics.py` — `GenerationMetrics` in-memory accumulator; per-service buckets; `summary()` returns totals, cache stats, per-service stats; `METRICS` global singleton; `reset()` for test isolation

#### Tests (109 new tests — 595 total, 1 skipped)
- `tests/test_prompt_cache.py` — 12 tests: mtime tracking, automatic reload, clear_cache, multi-prompt independence, real prompt files
- `tests/test_prompt_registry.py` — 23 tests: register/get/validate/list_names, error cases, DEFAULT_PROMPT_REGISTRY built-in entries
- `tests/test_service_registry.py` — 24 tests: register/get/create_all, error cases, DEFAULT_SERVICE_REGISTRY, AIServiceManager DI
- `tests/test_observability.py` — 48 tests: Timer API, all 9 event types, GenerationMetrics counters/aggregates/reset, METRICS global
- `tests/test_generation_models.py` — 5 new tests for `generation_id` (UUID4, uniqueness, explicit override, serialization)

### Changed

#### Performance & Architecture
- `generation/services/base_service.py` — Removed instance-level `self._loaded_prompt` cache; `generate()` now always calls `self._prompt_loader.load(prompt_name)`. PromptLoader is the single cache. Enables mtime invalidation end-to-end. Adds observability events (`GenerationStarted`, `GenerationCompleted`, `GenerationFailed`, `RetryStarted`, `ValidationFailed`).
- `tests/test_generation_services.py` — `TestPromptCaching` updated: `test_prompt_loaded_only_once_across_multiple_generate_calls` renamed to `test_prompt_loader_called_on_every_generate` with corrected `call_count == 3` assertion. New `test_prompt_loader_cache_serves_repeated_loads` verifies PromptLoader caching.

### Architecture Decisions (ADR-021 through ADR-025)
- ADR-021: Mtime-aware prompt cache invalidation (PromptLoader + removal of BaseAIService dual-cache)
- ADR-022: PromptRegistry for domain-level prompt discovery and validation
- ADR-023: ServiceRegistry for open/closed service registration
- ADR-024: `generation_id` UUID4 correlation key in ServiceMetadata
- ADR-025: Lightweight in-process observability layer (no Prometheus, no cloud)

---

## [Sprint 6] 2026-07-10 — Production Database Layer

### Added

#### ORM Models (26 tables)
- `database/base.py` — `Base(DeclarativeBase)` — shared declarative base
- `database/mixins.py` — 4 composable mixins: `UUIDPrimaryKeyMixin`, `TimestampMixin`, `SoftDeleteMixin`, `AuditUserMixin` (plain UUID audit columns, no FK — ADR-026)
- `database/models/reference.py` — `Trade`, `ConstructionStage`, `MaterialCategory`, `PPEType` (lookup tables)
- `database/models/company.py` — `Company` (multi-tenancy root), `User`
- `database/models/worker.py` — `Worker` (company_id RESTRICT, trade_id SET NULL)
- `database/models/project.py` — `Project`, `Site`, `ProjectWorker` (junction with UniqueConstraint)
- `database/models/audio.py` — `AudioFile`, `SpeechTranscript` (one-to-one, UNIQUE FK)
- `database/models/daily_log.py` — `DailyLog` with 12 JSON blobs (ADR-028) + 11 child relationships
- `database/models/log_items.py` — 11 normalized child tables (trades, work items, WIP, materials×3, equipment, incidents, hazards, delays, inspections)
- `database/models/generation.py` — `GenerationOutput` (Sprint 5 integration), `AuditLog` (immutable, ADR-030)

#### Repository Pattern
- `database/repositories/base.py` — `BaseRepository[T]` generic CRUD (get, list, count, exists, create, update, soft_delete, restore, hard_delete)
- `database/repositories/company.py` — `CompanyRepository` (get_by_slug, slug_exists), `UserRepository` (get_by_email, list_by_company)
- `database/repositories/project.py` — `ProjectRepository`, `SiteRepository`, `ProjectWorkerRepository`
- `database/repositories/worker.py` — `WorkerRepository` (find_by_name — voice extraction integration)
- `database/repositories/audio.py` — `AudioRepository` (mark_status, get_with_transcript), `SpeechTranscriptRepository`
- `database/repositories/daily_log.py` — `DailyLogRepository` (get_with_children with selectinload, create_from_extraction_result, review lifecycle: submit/approve/reject)
- `database/repositories/generation.py` — `GenerationRepository` (create_from_service_output with duck typing), `AuditLogRepository` (log_event, list_for_entity)

#### Alembic Migrations
- `alembic.ini` — Alembic configuration; reads DATABASE_URL from environment
- `database/migrations/env.py` — Side-effect imports all models for metadata population; naming conventions; NullPool
- `database/migrations/versions/001_initial_schema.py` — All 26 tables with PostgreSQL-native JSONB, UUID, TIMESTAMPTZ

#### Seed Scripts
- `database/seed/reference_data.py` — Idempotent seed: 25 trades, 22 construction stages, 16 material categories, 16 PPE types
- `database/seed/sample_data.py` — Fixed-UUID demo data: 1 company, 1 user, 3 workers, 1 project, 1 site, 1 approved DailyLog with full child records

#### Tests (123 new tests — 718 total, 1 skipped)
- `tests/test_db_models.py` — 46 ORM model tests: UUID PKs, mixins, relationships, UniqueConstraints, cascade deletes
- `tests/test_db_repositories.py` — 50 repository tests: CRUD, soft delete, review lifecycle, find_by_name, get_with_children, create_from_extraction_result, audit log
- `tests/test_db_seed.py` — 27 seed tests: exact record counts, idempotency (run twice = same counts), code value spot-checks, FK integrity

#### Documentation
- `docs/DATABASE_ARCHITECTURE.md` — Full ASCII ER diagram, ADR-026 through ADR-030, table reference, repository pattern guide, migration guide

### Architecture Decisions (ADR-026 through ADR-030)
- ADR-026: AuditUserMixin without FK constraints (circular dependency avoidance — companies↔users)
- ADR-027: Denormalized transcript on DailyLog (avoids 3-table join in 99% of API responses)
- ADR-028: JSON blobs vs child tables (queryable arrays → tables; always-fetched-whole → JSON)
- ADR-029: Soft delete pattern for mutable business entities (foreman error recovery)
- ADR-030: AuditLog immutability (no updated_at, no soft delete — OSHA/compliance requirement)

### Bug Fixes
- Renamed `AuditLog.metadata` → `AuditLog.event_metadata` (SQLAlchemy DeclarativeBase reserves `metadata` as a class attribute)

---

## [Sprint 5.0] 2026-07-08 — AI Generation Service Layer

### Added

#### generation/ Package
- `generation/__init__.py` — Public API (AIServiceManager + all output types)
- `generation/config.py` — `GenerationConfig` + `GenerationGroqConfig`; mirrors `ExtractionConfig` structure for `EngineFactory` duck-typing compatibility
- `generation/manager.py` — `AIServiceManager`: single orchestration point; receives `ConstructionDailyLog` dict, routes to all 4 services, returns `GenerationResult`
- `generation/models/outputs.py` — Pydantic v2 output models: `ServiceType` (enum), `ServiceMetadata`, `ServiceOutput`, `DailyReport`, `CustomerUpdate`, `ToolboxTalk`, `MaterialReminder`, `GenerationResult`
- `generation/prompts/loader.py` — `PromptLoader`: loads versioned `.md` prompts with YAML-like frontmatter; per-instance caching; zero external dependencies
- `generation/prompts/daily_report.md` — v1.0.0 formal contractor daily report prompt
- `generation/prompts/customer_update.md` — v1.0.0 client-facing email prompt
- `generation/prompts/safety_talk.md` — v1.0.0 OSHA-referenced safety toolbox talk prompt
- `generation/prompts/material_reminder.md` — v1.0.0 procurement reminder prompt
- `generation/services/base_service.py` — `BaseAIService` abstract class (Template Method pattern): load prompt → build user message → call LLM with retry → validate → return typed output
- `generation/services/daily_report.py` — `DailyReportService`
- `generation/services/customer_update.py` — `CustomerUpdateService`
- `generation/services/safety_talk.py` — `SafetyTalkService`
- `generation/services/material_reminder.py` — `MaterialReminderService`
- `generation/validators/content_validator.py` — `ContentValidator`: 6 AI output quality checks (empty, min/max length, required phrases, placeholder detection, duplicate sentences, markdown structure)

#### CLI
- `report.py` — Sprint 5 CLI entry point: accepts `ExtractionResult` JSON or raw `ConstructionDailyLog`; flags: `--service`, `--output`, `--stdin`, `--check`, `--provider`

#### Tests (164 new tests — all pass without GROQ_API_KEY)
- `tests/test_generation_models.py` — 27 tests for all Pydantic output models
- `tests/test_generation_config.py` — 14 tests for config defaults, env overrides, duck-typing compatibility
- `tests/test_generation_prompts.py` — 22 tests for prompt loading, frontmatter parsing, caching
- `tests/test_content_validator.py` — 23 tests for all 6 content validation checks
- `tests/test_generation_services.py` — 25 tests for all 4 services, retry logic, prompt caching
- `tests/test_generation_manager.py` — 19 tests for orchestration, DI, serialization

#### Documentation
- `docs/AI_SERVICES.md` — Complete Sprint 5 framework reference (architecture, models, config, usage examples, prompt format, validation, extensibility guide, ADR summary, test coverage table)

#### Infrastructure
- `data/generated/.gitkeep` — Output directory for runtime-generated files (git-ignored)
- `pydantic==2.13.4` added to `requirements-dev.txt`
- `GENERATION_*` env vars added to `.env.example`
- `data/generated/*` added to `.gitignore` (with `.gitkeep` exception)

### Changed
- `docs/ROADMAP.md` — Sprint 5 marked complete with full deliverable list
- `docs/HANDOVER.md` — Updated to Sprint 5 complete state
- `docs/NEXT_SPRINT.md` — Updated to Sprint 6 spec
- `docs/PROJECT_STATE.md` — Updated sprint status and repo structure

### Architecture Decisions (ADR-017 through ADR-020)
- ADR-017: Prompts as versioned `.md` files (product artifacts, not code)
- ADR-018: Pydantic for generation output models (Sprint 7 FastAPI readiness)
- ADR-019: One shared engine, system instructions embedded in user message (Sprint 4 FROZEN interface respected)
- ADR-020: Prompts in `generation/prompts/` not `app/prompts/` (`app/` is Sprint 7's directory)

---

## [Sprint 1.1] 2026-06-30 — Sprint 1 Freeze & Knowledge Base Extension

### Added
- `knowledge/construction_rules.json` — 38 machine-readable construction rules (sequential, parallel, material consistency, worker consistency, safety constraints, weather constraints, quantity sanity)
- `knowledge/dependency_graph.json` — Complete DAG of residential construction workflow with 23 nodes, 33 edges, critical path, parallel groups, and topological sort
- `knowledge/validation_rules.json` — 35 machine-readable validation rules with conditions, severities, error messages, and suggested fixes (consumed by Sprint 2 generators and Sprint 4 AI validator)
- `knowledge/construction_ontology.json` — Complete entity-relationship ontology covering trades, materials, equipment, hazards, PPE, worker roles, inspection types, delay types, and weather conditions with 40+ relationships. Designed for future RAG/FAISS integration
- `docs/CHANGELOG.md` — This file (project change history)
- `docs/DECISIONS.md` — Architecture decision record
- `docs/PROJECT_STATE.md` — Official project state (moved from root to docs/)
- `docs/NEXT_SPRINT.md` — Sprint 2 preparation document
- `docs/ROADMAP.md` — Full product roadmap
- `docs/HANDOVER.md` — Complete handover document for new sessions

### Fixed (Sprint 1 Gaps Identified)
- Gap: `construction_stages.json` covered only 11 stages but `current_stage` schema enum had 22 values. The ontology and dependency graph now cover all 22 stages.
- Gap: Sequencing rules were embedded inside `construction_stages.json` as a sub-object. Extracted to dedicated `construction_rules.json`.
- Gap: No machine-readable validation for dataset generators. Resolved with `validation_rules.json`.
- Gap: No entity-relationship model for future AI/RAG use. Resolved with `construction_ontology.json`.

---

## [Sprint 1.0] 2026-06-30 — Sprint 1 Initial Delivery

### Added
- `knowledge/construction_stages.json` — Knowledge base for all 11 residential construction stages with workers, materials, tools, delays, safety hazards, and daily report fields
- `knowledge/construction_daily_log_schema.json` — Master ConstructionDailyLog JSON Schema v1.0.0 with 12 sections, 80+ fields, UUID keys, explicit null typing, enum validation, and complete example
- `docs/sprint_1/CONSTRUCTION_RESEARCH.md` — Human-readable domain research on all 11 stages
- `docs/sprint_1/SCHEMA_DESIGN.md` — Architecture decisions explaining schema design choices
- `README.md` — Project overview with tech stack and sprint progress
- `.gitignore` — Python, Node, Docker, and AI model ignore rules
- `.env.example` — Complete environment variable template for all future modules
- `PROJECT_STATE.md` (root) — Sprint 1 state document (frozen as Sprint 1 artifact)

---

## [Sprint 2.0] 2026-06-30 — Synthetic Construction Data Generation Framework

### Added

#### Framework Infrastructure
- `dataset_generation_framework/` — Production-grade, reusable data generation framework
- `dataset_generation_framework/config.py` — Single source of truth for all generation parameters. Change 5 size constants to scale from 5,000 to 500,000+ records.
- `dataset_generation_framework/core/knowledge_loader.py` — Singleton KnowledgeBase with O(1) lookup indexes for all 6 Sprint 1 knowledge files
- `dataset_generation_framework/core/stage_machine.py` — DAG-based construction project state machine (ProjectState + StageMachine). Enforces topological stage ordering from `dependency_graph.json`
- `dataset_generation_framework/core/rule_engine.py` — Query interface for `construction_rules.json`. Answers questions like "Can roofing and HVAC run in parallel?" and "What materials are expected for framing?"
- `dataset_generation_framework/validation/pipeline.py` — 4-phase ValidationPipeline (blocking → errors → warnings → info). Fail-fast on Phase 1.
- `dataset_generation_framework/generators/base_generator.py` — Abstract `BaseGenerator` with streaming yield, seeded RNG, and `GeneratorStats` tracking
- `dataset_generation_framework/exporters/jsonl_exporter.py` — Batched JSONL file writer with context manager API
- `dataset_generation_framework/exporters/csv_exporter.py` — Batched CSV writer with auto-inferred headers, None→"", list→";" conversion
- `dataset_generation_framework/statistics/report_generator.py` — Post-generation statistical analysis and summary report

#### Dataset Generators
- `dataset_generation_framework/generators/daily_log_generator.py` — Simulates complete construction projects day-by-day to produce `ConstructionDailyLog` records. Uses StageMachine + RuleEngine to guarantee sequencing correctness.
- `dataset_generation_framework/generators/schedule_generator.py` — Generates project schedules with planned vs. actual dates and delay breakdown
- `dataset_generation_framework/generators/safety_talk_generator.py` — Generates safety toolbox talk records from OSHA knowledge and ontology hazards
- `dataset_generation_framework/generators/material_generator.py` — Generates construction material catalog entries from ontology
- `dataset_generation_framework/generators/customer_update_generator.py` — Generates (raw foreman notes, customer email) training pairs

#### Entry Point
- `generate.py` — CLI entry point: `python generate.py`, `python generate.py --dataset daily_logs --count 5000 --seed 42`

#### Tests
- `tests/test_knowledge_loader.py` — Unit tests for KnowledgeBase singleton, all API domains
- `tests/test_stage_machine.py` — Unit tests for StageMachine, ProjectState, can_start(), advance_day()
- `tests/test_validation_pipeline.py` — Unit tests for ValidationResult, 4-phase pipeline, all rule types
- `tests/test_generators.py` — Unit tests for all 5 generators (count, keys, range validation, reproducibility)
- `tests/test_integration.py` — End-to-end pipeline tests (generator → exporter → file → read-back validation)

#### Dataset Infrastructure
- `datasets/raw/`, `datasets/generated/`, `datasets/validated/`, `datasets/exports/` — Dataset directory structure
- `datasets/README.md` — Dataset documentation: format, schema, purpose, generation commands
- `requirements-dev.txt` — Python development dependencies (jsonschema, faker, pytest, pytest-cov, tqdm)

### Architecture Decisions (Sprint 2)
- ADR-009: Production framework architecture over one-off scripts (see DECISIONS.md)
- ADR-010: Project simulation over random record generation (see DECISIONS.md)
- ADR-011: Streaming generators — same peak memory at 500k as at 5k (see DECISIONS.md)

---

## [Sprint 3.0] 2026-07-01 — Speech Processing Framework

### Added

#### Framework Infrastructure
- `speech/` — Standalone, engine-agnostic Speech Processing Framework. Zero imports from `dataset_generation_framework/` or `knowledge/`. Public API: `SpeechProcessingPipeline.process(audio_path) -> SpeechProcessingResult`
- `speech/config.py` — `SpeechProcessingConfig` with nested `AudioValidationConfig`, `WhisperConfig`, `PreprocessingConfig`, `PostprocessingConfig`. `from_env()` reads `SPEECH_WHISPER_MODEL_SIZE`, `SPEECH_WHISPER_DEVICE`, `SPEECH_WHISPER_COMPUTE_TYPE`, `SPEECH_WHISPER_LANGUAGE`, `SPEECH_MAX_FILE_SIZE_MB`, `SPEECH_MAX_DURATION_SECONDS`, `SPEECH_ENABLE_NOISE_REDUCTION`, `SPEECH_MODELS_DIR`
- `speech/utils/constants.py` — Framework-wide constants (supported formats, size/duration limits, filler words, construction term corrections)
- `speech/utils/retry.py` — Exponential backoff `@retry` decorator for transient STT failures
- `speech/pipeline.py` — `SpeechProcessingPipeline`, the main orchestrator: validation → preprocessing → STT → postprocessing → result. Supports single-file `process()` and `process_batch()`. Same API from 1 recording to 100,000+

#### Data Models
- `speech/models/transcript.py` — `WordTimestamp`, `TranscriptSegment`, `Transcript` dataclasses. The permanent, engine-neutral contract between any STT engine and the rest of the framework
- `speech/models/metadata.py` — `AudioFileInfo`, `ProcessingStats`, `SpeechProcessingMetadata` — full audit trail for every pipeline run
- `speech/models/processing_result.py` — `AudioValidationResult`, `SpeechProcessingResult`. Structured object returned by every `process()` call, never plain text. `to_dict()`/`to_json()` for lossless serialization

#### Audio Loading & Validation
- `speech/loaders/format_detector.py` — Format detection via extension + magic-byte fallback, independent of file extension correctness
- `speech/loaders/audio_loader.py` — Audio metadata extraction via soundfile (WAV/FLAC/OGG) with librosa fallback (MP3/M4A). Graceful degradation to `is_readable=False` if neither package is installed
- `speech/validators/audio_validator.py` — 8 blocking pre-transcription checks (existence, size, format, readability, duration, sample rate, channels) + 3 non-blocking warnings, run before any transcription attempt

#### Preprocessing
- `speech/preprocessors/audio_normalizer.py` — Peak normalization to -3 dBFS; no-op fallback if numpy/soundfile unavailable
- `speech/preprocessors/noise_reducer.py` — Optional `noisereduce`-based noise reduction; disabled by default, no-op pass-through if package missing
- `speech/preprocessors/chunker.py` — `AudioChunker` reports expected chunk boundaries for long recordings (Whisper handles actual chunking internally)

#### STT Engine
- `speech/whisper/engine.py` — `BaseSTTEngine` abstract interface + `FasterWhisperEngine` implementation. `faster_whisper` is imported in this file only — nowhere else in the codebase. Lazy model loading (model loads on first `transcribe()` call, not at construction). Wrapped in `@retry` for transient load failures

#### Postprocessing
- `speech/postprocessors/construction_normalizer.py` — Pattern-based construction terminology correction (`re bar` → `rebar`, `h v a c` → `HVAC`, `p v c` → `PVC`, etc.). Pure text correction, zero domain knowledge
- `speech/postprocessors/transcript_cleaner.py` — `TranscriptCleaner` drops Whisper hallucination artifacts (`[INAUDIBLE]`, `[Music]`, YouTube-style artifacts), strips filler words, applies construction normalization. Returns new `Transcript`, never mutates input

#### Metadata & Export
- `speech/metadata/extractor.py` — `MetadataExtractor` builds `SpeechProcessingMetadata` at pipeline start, finalizes processing stats after transcription completes
- `speech/exporters/base_exporter.py` — `BaseExporter` abstract interface for result exporters
- `speech/exporters/json_exporter.py` — `JSONExporter` (full structured JSON) and `JSONLExporter` (append-mode, one line per result, for batch runs)
- `speech/exporters/text_exporter.py` — `TextExporter` (plain transcript text) and `VerboseTextExporter` (timestamps + confidence + metadata header)

#### CLI
- `transcribe.py` — CLI entry point. Single file, `--batch DIR` mode, `--dry-run` validation-only mode, `--format json|jsonl|text|verbose-text`, `--model`/`--device`/`--compute-type` overrides

#### Tests
- `tests/conftest.py` — Synthetic WAV generation (sine tones via numpy+soundfile, stdlib `wave` fallback), shared fixtures for valid/short/long/stereo/empty/fake audio
- `tests/test_speech_models.py` — Data model construction, serialization round-trips
- `tests/test_speech_config.py` — Default config, constructor overrides, `from_env()` env-var reading
- `tests/test_speech_validator.py` — All 8 blocking checks + 3 warnings, boundary cases
- `tests/test_transcript_cleaner.py` — Filler removal, hallucination dropping, construction-term normalization
- `tests/test_audio_pipeline.py` — Full pipeline integration via injected `MockSTTEngine` (no GPU, no model download, no network); real-engine tests gated `@pytest.mark.skipif(not HAS_FASTER_WHISPER, ...)`

#### Sample Data
- `scripts/create_sample_audio.py` — Generates 10 synthetic sine-tone WAV files covering validator boundary conditions (short/long duration, stereo, low/high sample rate, chunk boundaries)
- `data/sample_audio/` — 10 synthetic WAV files + ground-truth placeholder `.txt` files + `README.md` explaining synthetic vs real audio and how to add real recordings for WER testing
- `data/transcripts/raw/`, `data/transcripts/cleaned/` — Output directories for CLI transcription runs (gitkept, generated content gitignored)

#### Documentation
- `docs/AI_PIPELINE.md` — Full application AI pipeline reference: speech → extraction → validation → persistence → delivery, what exists vs. what's planned
- `docs/SPEECH_PIPELINE.md` — Speech Processing Framework reference: architecture, pipeline stages, public API, configuration, CLI, testing

#### Dependencies
- `requirements-dev.txt` — Added `numpy`, `soundfile`, `faster-whisper`, `librosa`, `noisereduce`, `jiwer`. All free, open source, no paid APIs

### Fixed
- `speech/pipeline.py` passed `chunk_overlap_seconds=` to `AudioChunker.__init__()`, which expects `overlap_seconds=`. Fixed during Sprint 3 test verification.

### Architecture Decisions (Sprint 3)
- ADR-012: Engine-agnostic speech framework via `BaseSTTEngine` abstraction (see DECISIONS.md)
- ADR-013: Lazy model loading for STT engines (see DECISIONS.md)
- ADR-014: `SpeechProcessingResult` as a structured object, never plain text (see DECISIONS.md)

---

## [Sprint 4.0] 2026-07-04 — AI Information Extraction Framework

### Added

#### Framework Infrastructure
- `extraction/` — Standalone, engine-agnostic AI Extraction Framework. Zero imports from `speech/`, `dataset_generation_framework/`, or `knowledge/` except via well-defined interfaces. Public API: `ExtractionPipeline.extract(transcript_text) -> ExtractionResult`
- `extraction/config.py` — `ExtractionConfig` with nested `OllamaConfig`. `from_env()` reads `EXTRACTION_OLLAMA_MODEL`, `EXTRACTION_OLLAMA_HOST`, `EXTRACTION_OLLAMA_TEMPERATURE`, `EXTRACTION_OLLAMA_TIMEOUT`, `EXTRACTION_MAX_RETRIES`, `EXTRACTION_KNOWLEDGE_DIR`
- `extraction/pipeline.py` — `ExtractionPipeline` orchestrator: build prompt → call engine → parse JSON → validate → return `ExtractionResult`. Supports `extract(text)` and `extract_from_speech_result(SpeechProcessingResult)`. Retry with exponential backoff for LLM call failures.

#### Data Models
- `extraction/models/extraction_result.py` — `ExtractionResult` and `ExtractionMetadata` dataclasses. Structured result for every extraction run, never a raw dict. `to_dict()`/`to_json()` for lossless serialization. `ExtractionResult.failure()` factory ensures every code path returns a complete, serializable result.

#### Extraction Engine
- `extraction/engines/base_engine.py` — `BaseExtractionEngine` abstract interface (`extract()`, `is_available()`, `model_name`, `host`). The only interface extraction business logic and tests depend on.
- `extraction/engines/ollama_engine.py` — `OllamaEngine` implementation. The ONLY file in the codebase that calls Ollama's REST API (`POST /api/chat`). Uses `requests` (already a transitive dependency) — no separate `ollama` Python package needed. Graceful `is_available()` check before every extraction run.

#### Prompt Engineering
- `extraction/prompts/system_prompt.txt` — System prompt instructing the LLM to extract only mentioned fields, use exact enum values, output pure JSON, and signal `{"extraction_possible": false}` for unusable transcripts.
- `extraction/prompts/builder.py` — `PromptBuilder` builds per-run extraction prompts with schema-derived context (stage enums, weather enums, trade enums, field reference). Constructed once per pipeline; `build_prompt()` called per extraction.

#### Postprocessing
- `extraction/postprocessors/json_repairer.py` — `repair_json()` extracts valid JSON from raw LLM output via three strategies: direct parse, markdown fence extraction (` ```json ... ``` `), and outermost-brace search. Returns `(dict, was_repaired)`. `JSONRepairError` on total failure.

#### Validation
- `extraction/validators/schema_validator.py` — `SchemaValidator` runs two-stage validation: JSON Schema structural check (via `jsonschema`) then Sprint 2 `ValidationPipeline` business rules (`applies_to="ai_extraction"`). Reuses existing validation logic with zero duplication.

#### CLI
- `extract.py` — CLI entry point. Extract from a Sprint 3 `SpeechProcessingResult` JSON file, from `--text` string, or check engine availability with `--check`. Supports `--model`, `--host`, `--output`, `--log-date` overrides.

#### Tests
- `tests/test_extraction_models.py` — `ExtractionResult` and `ExtractionMetadata` construction, serialization, accessors, failure factory
- `tests/test_extraction_config.py` — Default config values, `from_env()` env-var reading, partial overrides
- `tests/test_json_repairer.py` — All three repair strategies, boundary cases, error cases
- `tests/test_extraction_pipeline.py` — Full pipeline integration via injected `MockExtractionEngine` (no Ollama, no network, no GPU). Failure modes, JSON repair, `extract_from_speech_result()`, real-Ollama test gated with `skipif`

### Architecture Decisions (Sprint 4)
- ADR-015: Engine-agnostic extraction framework via `BaseLLMProvider` + `EngineFactory` (see DECISIONS.md)
- ADR-016: `ExtractionResult` as a structured object, never a raw dict (see DECISIONS.md)

---

## [Sprint 4.1] 2026-07-06 — Groq Migration + Provider-Agnostic Factory

### Changed

#### Architecture
- Replaced `OllamaEngine` with `GroqEngine` (Groq cloud API, free tier). No disk-resident model required.
- Renamed `BaseExtractionEngine` → `BaseLLMProvider` throughout.
- Introduced `EngineFactory` in `extraction/engines/factory.py`: registry-based factory so `ExtractionPipeline` is provider-blind. Adding a future provider requires only: implement `BaseLLMProvider`, add config, register in factory — zero pipeline changes.
- Renamed `OllamaConfig` → `GroqConfig`; added `provider: str = "groq"` field to `ExtractionConfig`.
- Renamed `ExtractionMetadata.ollama_host` → `engine_endpoint`.
- Removed `--host` CLI flag (Ollama-specific); added `--provider` flag.

#### Removed
- `extraction/engines/ollama_engine.py` — deleted (no Ollama code remains in repo).
- `requests` dependency — was only needed for Ollama REST calls; `groq` package uses httpx.

#### Added
- `extraction/engines/factory.py` — `EngineFactory` with `register()`, `create_from_config()`, `available()`.
- `groq` Python package added to `requirements-dev.txt`.
- `GROQ_API_KEY` env var in `.env` (gitignored) and `.env.example`.
- `TestEngineFactory` test class: registration, creation, unknown-provider error, custom-provider registration/cleanup.

### Architecture Decisions
- ADR-015 revised: documents `BaseLLMProvider` + `EngineFactory` pattern (see DECISIONS.md)
