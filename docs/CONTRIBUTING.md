# Contributing to Construction Site AI

This document defines the conventions this codebase already follows, so new code stays consistent with everything already here. It is descriptive of established patterns (Sprints 1–7), not a wishlist.

---

## 1. Coding Standards

- **Type hints everywhere.** Every function signature has parameter and return types. `from __future__ import annotations` at the top of every module (already the convention across all Sprints).
- **Docstrings explain WHY, not WHAT.** A one-line summary is fine for a trivial function. For anything with a non-obvious design choice, the docstring explains the reasoning and the alternative that was rejected — see almost any file in `app/` or `database/` for the pattern. Do not write a docstring that just restates the function name in prose.
- **No comments for comments' sake.** Inline comments are reserved for a genuinely non-obvious constraint (a workaround, a subtle invariant) — not for narrating what the next line does.
- **Structured results over exceptions for expected failure modes.** `SpeechProcessingResult`, `ExtractionResult`, `GenerationResult` all carry `.success`/`.errors` instead of raising for "the LLM was unreachable" or "validation failed." Follow this pattern for any new pipeline-stage function. Exceptions are reserved for genuinely unexpected failures and for HTTP-layer control flow (`HTTPException`, `ValueError` for repository business-rule violations — see `docs/BACKEND_ARCHITECTURE.md` §6).
- **No premature abstraction.** Three similar lines are better than a shared helper introduced for a single caller. Don't build a class where a function suffices (see `app/api/v1/auth.py`'s docstring for a worked example of this reasoning).

---

## 2. Folder Conventions

| Package | What belongs here | What does NOT belong here |
|---|---|---|
| `speech/`, `extraction/`, `generation/`, `database/` | Sprint 1–6 core pipeline. FROZEN — see §5. | Anything HTTP-related, anything importing `app/`. |
| `app/core/` | Cross-cutting config and security primitives with no HTTP awareness. | Route handlers, repository calls to specific resources. |
| `app/api/dependencies.py` | `Depends()`-injectable callables shared across routers. | Business logic — a dependency fetches/validates, it doesn't orchestrate. |
| `app/api/v1/*.py` | One file per resource. Route handlers only — translate HTTP in, call a repository or service, translate the result back out. | SQL, multi-step orchestration (belongs in `app/services/`). |
| `app/services/*.py` | Multi-step business logic that chains repository calls and/or Sprint 1–6 pipeline calls. | Anything that touches `Request`/`Response` objects directly. |
| `app/schemas/*.py` | Pydantic request/response models. One file per resource, mirroring `app/api/v1/`. | SQLAlchemy imports — schemas describe the HTTP contract, not storage. |
| `app/middleware/*.py` | Cross-cutting request/response processing (logging, request ID, exception mapping, CORS). | Resource-specific logic. |
| `database/repositories/*.py` | All SQL. The only layer that imports SQLAlchemy's `Session`/`select`/etc. | HTTP status codes, Pydantic models, anything importing `app/` (see `docs/BACKEND_ARCHITECTURE.md` §8). |
| `tests/` | One `test_<module>.py` per source module being tested, mirroring the source tree. `test_api_*.py` for `app/` endpoint tests specifically. | — |

---

## 3. Branch Strategy

This project develops on `main` directly, with each sprint's work committed incrementally and tagged on completion (`sprint-N-complete`, or `sprint-N-final` if a hardening pass followed). There is no long-lived `develop` branch. If you are adding a feature within an already-approved sprint's scope, commit directly to `main`; if you are prototyping something exploratory, use a short-lived feature branch and merge (not rebase-and-force-push) back into `main` once it's ready.

---

## 4. Commit Message Format

This repository follows **Conventional Commits**:

```
<type>(<optional scope>): <short summary>

<body — the WHY, not a line-by-line diff summary>
```

Types used in this codebase's history: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`. Scope is often the package touched (`fix(db): ...`, `feat(api): ...`). Look at `git log --oneline` for concrete examples — e.g. `feat(db): Sprint 6 — production database persistence layer`, `fix: harden LLM null handling and correct generation metadata mapping`.

The body should explain why a change was made, not restate the diff — a reviewer (or future you) can already see *what* changed; they need to know *why*. No AI-attribution lines in commit messages for this project.

---

## 5. Sprint Freeze Discipline

Sprints 1–6 are FROZEN. Do not modify code inside `knowledge/`, `dataset_generation_framework/`, `speech/`, `extraction/`, `generation/`, or `database/` unless you are fixing a **verified bug** — and when you do, the commit message should say so explicitly (see `fix: full Sprint 6 hardening pass — null guards, dead code, doc drift` for the pattern: a precise description of each bug and its fix, not a vague "cleanup").

Additive changes to a frozen package (a new function, a new file that doesn't change existing behavior) are the one exception this project has already made twice: `database/session.py` gained `get_async_session()` in Sprint 7 without touching the existing sync path, and `database/seed/sample_data.py` gained a placeholder `DEV_ADMIN_ID` row without changing any existing seeded record. If you need to add to a frozen package, keep the addition isolated and clearly documented as additive in both the code and the commit message.

---

## 6. How To Add a New API Endpoint

1. **Decide the version.** Adding to an existing resource's contract in a backward-compatible way (a new optional field, a new endpoint on an existing resource) goes in `app/api/v1/`. A breaking change to an existing endpoint's contract means a new `app/api/v2/` package instead — v1 stays untouched (see `docs/BACKEND_ARCHITECTURE.md` §5).
2. **Add or extend the schema** in `app/schemas/<resource>.py`. Request models validate input; response models use `ConfigDict(from_attributes=True)` if built from an ORM object (`Model.model_validate(orm_instance)`).
3. **Add the route** in `app/api/v1/<resource>.py`. Inject `session: Session = Depends(get_db)` for DB access, `user: CurrentUser = Depends(get_current_user)` if the endpoint requires auth (almost everything except `/health/*` and `/auth/login`), `Depends(require_role(...))` if it's role-restricted.
4. **If it's a single repository call**, put the logic directly in the route handler (see `app/api/v1/daily_logs.py:get_daily_log`). **If it's multi-step orchestration**, extract it into `app/services/<name>_service.py` (see `app/services/pipeline_service.py`) and call that function from the route.
5. **Wrap the return value** in `success_response(data, message=...)` — never return a bare Pydantic model or dict; the envelope is mandatory (`docs/BACKEND_ARCHITECTURE.md` §6).
6. **Register the router** in `app/create_app.py` if it's a new file (`app.include_router(...)`), or it's already registered if you extended an existing router file.
7. **Write tests** in `tests/test_api_<resource>.py` using the `tests/conftest_api.py` fixtures (`api_client`, `auth_headers`, `seeded_session`). Cover: the happy path, the 401 case (no/bad token), the 404 case (resource doesn't exist), and any business-rule 409 the endpoint can trigger.
8. **Manually verify** via Swagger UI (`docs/BACKEND_STARTUP.md` §7) before considering the endpoint done — the automated test suite catches contract bugs; only a real running server catches environment/startup bugs (see `docs/BACKEND_ARCHITECTURE.md` §9 for why this step is not optional).

---

## 7. How To Add a New AI Service (Generation)

Sprint 5's `generation/` package (frozen) already has this pattern established — a new AI-generated document type follows the same shape as the existing four (`daily_report`, `customer_update`, `safety_talk`, `material_reminder`):

1. Add a new `ServiceType` enum value in `generation/models/outputs.py`.
2. Add a new output model subclassing `ServiceOutput` (mirrors `DailyReport`, `CustomerUpdate`, etc.).
3. Add a new service class subclassing `BaseAIService` in `generation/services/`, implementing `service_type`, `prompt_name`, `_build_user_message()`.
4. Add the corresponding prompt template `.md` file in `generation/prompts/`.
5. Register the new service in `generation/services/registry.py`'s `DEFAULT_SERVICE_REGISTRY`.
6. `AIServiceManager.generate_all()` picks it up automatically once registered — no changes needed there.
7. **This is Sprint 5 territory** — per §5 above, only touch it for a verified bug or an explicitly approved new-service addition, and update `app/services/pipeline_service.py` and `app/api/v1/daily_logs.py:trigger_generation()` to include the new output type in their persistence loop.

---

## 8. How To Create a Migration

```powershell
.\venv\Scripts\python.exe -m alembic revision --autogenerate -m "short description of the schema change"
```

1. Make your model change in `database/models/*.py` first.
2. Run the command above — Alembic diffs `Base.metadata` (which includes your change, since `database/migrations/env.py` imports `database.models` to populate it) against the live database schema and generates a migration file in `database/migrations/versions/`.
3. **Review the generated file manually.** Autogenerate is not always correct — it can miss `CHECK` constraints, get column-type changes wrong, or fail to detect a renamed column (interpreting it as a drop + add, which loses data on a real database). See `database/base.py`'s naming-convention comment for why constraint names are deterministic — this makes generated migrations more reviewable.
4. Apply it: `python -m alembic upgrade head`.
5. Update `tests/test_db_models.py` and/or `tests/test_db_repositories.py` to cover the new column/table.
6. If this is a Sprint 1–6 schema change (not a new Sprint 7+ table), it falls under the §5 freeze discipline — document it as a verified-bug fix.

---

## 9. How To Write Tests

- **Sprint 1–6 (`speech/`, `extraction/`, `generation/`, `database/`) tests**: SQLite in-memory for anything DB-related (`DatabaseConfig.for_testing()`), `MockExtractionEngine`/similar for anything LLM-related — no live PostgreSQL or Groq API calls in the automated suite (those are verified manually, as documented in `docs/WORKING_STATE.md`).
- **`app/` API tests**: use `tests/conftest_api.py`'s fixtures. `api_client` gives you a `TestClient` wired to an isolated in-memory database (`Base.metadata.create_all()` + Sprint 6 seed functions run fresh per test). `auth_headers` gives you a ready-to-use Bearer token for the seeded dev-admin account. Do not write a test that depends on the real `.env`/PostgreSQL — that breaks CI portability, which is the entire reason Sprint 6 established the SQLite-in-memory pattern in the first place.
- **Naming**: `test_<Thing>_<condition>_<expected outcome>`, grouped into `class Test<Thing>:` blocks — see any existing `tests/test_api_*.py` file for the established style.
- **Isolation gotcha to know about**: `database.session.get_session()`/`get_engine()` cache a module-level singleton. If a test monkeypatches `get_engine` to point at a different in-memory database than a previous test used, you must call `database.session.reset_engine()` (sync) — see `tests/test_app_dev_seed.py`'s `_reset_session_factory` fixture for the pattern, and its docstring for the failure mode it prevents.
- Run the full suite before considering any change done: `pytest tests/ -q`. Current baseline: **777 passed, 1 skipped**.
