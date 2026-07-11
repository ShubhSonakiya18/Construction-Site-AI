# Backend Startup Guide

Every step below was run and verified working during Sprint 7 development — this is not aspirational documentation. Commands are shown for Windows PowerShell (this project's primary shell); Bash equivalents are noted where they differ.

---

## 1. Prerequisites

- Python 3.12+, venv already created at `venv/` with `requirements-dev.txt` installed (see `docs/PROJECT_STATE.md` if starting from a completely fresh clone).
- PostgreSQL 15 running locally. See `docs/WORKING_STATE.md` §4 if you need to set this up from scratch.
- A `.env` file in the project root (copy from `.env.example`) with at minimum:
  ```
  GROQ_API_KEY=gsk_...
  DATABASE_URL=postgresql://postgres:<password>@localhost:5432/construction_site_ai
  ```
  If `<password>` contains an `@`, URL-encode it as `%40`.

---

## 2. Start PostgreSQL

```powershell
Get-Service postgresql-x64-15 | Start-Service   # if not already running
```

Verify it's listening on the port your `DATABASE_URL` expects:
```powershell
Get-NetTCPConnection -LocalPort 5432 -State Listen
```

---

## 3. Apply Alembic Migrations

Builds all 26 tables (+ `alembic_version`) if they don't already exist:

```powershell
.\venv\Scripts\python.exe -m alembic upgrade head
```

Verify:
```powershell
.\venv\Scripts\python.exe -m alembic current
```
Expect `001 (head)`.

> **Known gotcha:** running `alembic` directly reads `alembic.ini`'s fallback `sqlalchemy.url` (a placeholder), not your real `.env`. If you see a password-authentication error here, it's this fallback being used — the app itself never hits this path (see §5). To run Alembic with your real credentials from the shell, set `DATABASE_URL` in your shell session first, or use the migration exactly as shown above (the `%` escaping in `database/migrations/env.py` already handles a `%40`-encoded password from `.env`).

---

## 4. Seed Reference Data + Sample Data + Dev Admin Login

Three seed layers, in order:

```powershell
.\venv\Scripts\python.exe -m app.core.dev_seed
```

This one command runs all three:
1. `seed_all_reference_data()` — 25 trades, 22 construction stages, 16 material categories, 16 PPE types (idempotent — safe to re-run).
2. `seed_sample_data()` — 1 company, 2 users (an owner with no password, and the dev-admin placeholder), 3 workers, 1 project, 1 site, 1 approved daily log with full child data (idempotent).
3. `ensure_dev_admin_password()` — hashes and sets the password on the dev-admin user (idempotent — a second run is a no-op if the hash is already set).

Expect log output ending with:
```
INFO: Dev admin password set for admin@example.com (id=aaaaaaaa-0009-...). DEVELOPMENT USE ONLY — do not run against production.
```

**Default dev credentials:** `admin@example.com` / `Admin@123`. Override via `.env`:
```
DEV_SEED_ADMIN_EMAIL=your-email@example.com
DEV_SEED_ADMIN_PASSWORD=YourPassword123
```

> This account and this script are for local development only. Never run `python -m app.core.dev_seed` against a production database.

---

## 5. Start the FastAPI Application

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Expect:
```
INFO:     Started server process [...]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

`app/main.py` calls `load_dotenv()` before anything else, so `.env` is loaded into `os.environ` the same way every Sprint 1–6 CLI script already does — you do not need to export `DATABASE_URL`/`GROQ_API_KEY` into your shell manually. If you skip this step and see `RuntimeError: DATABASE_URL environment variable is not set`, you are running the app without going through `app/main.py` (or `.env` is missing/misplaced) — see `docs/BACKEND_ARCHITECTURE.md` §9 for why this matters.

`--reload` restarts the server on file changes — useful for development, omit it for anything closer to production.

---

## 6. Verify It's Alive

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/live
```
Expect `{"success":true,"data":{"status":"alive",...}}`. This endpoint does no I/O — if it fails, the process itself isn't running.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/ready
```
Expect `{"success":true,"data":{"status":"ready","database":true}}`. Failure here means PostgreSQL isn't reachable — recheck step 2.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```
Full diagnostic — checks both the database **and** the Groq extraction engine. Expect both components `"status":"up"`. If Groq shows `"down"`, check `GROQ_API_KEY` in `.env`.

---

## 7. Access Swagger UI and ReDoc

Open in a browser:
- **Swagger UI:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc
- **Raw OpenAPI schema:** http://127.0.0.1:8000/openapi.json

Swagger UI lets you try every endpoint interactively, including the auth flow:
1. `POST /api/v1/auth/login` with the dev credentials from step 4.
2. Copy the `access_token` from the response.
3. Click the **Authorize** button (top right) and paste the token (no `Bearer ` prefix needed — Swagger adds it).
4. Every subsequent request in the UI now carries the token.

---

## 8. Manual curl / Invoke-RestMethod Walkthrough

```powershell
# Login
$login = Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/auth/login `
    -ContentType "application/json" `
    -Body '{"email":"admin@example.com","password":"Admin@123"}'
$token = $login.data.access_token

# Get the seeded sample daily log
$headers = @{ Authorization = "Bearer $token" }
Invoke-RestMethod http://127.0.0.1:8000/api/v1/daily-logs/aaaaaaaa-0008-4000-8000-000000000008 -Headers $headers

# List daily logs for the seeded project
Invoke-RestMethod http://127.0.0.1:8000/api/v1/projects/aaaaaaaa-0006-4000-8000-000000000006/daily-logs -Headers $headers
```

Bash equivalent:
```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"Admin@123"}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['data']['access_token'])")

curl -s http://127.0.0.1:8000/api/v1/daily-logs/aaaaaaaa-0008-4000-8000-000000000008 \
  -H "Authorization: Bearer $TOKEN"
```

---

## 9. Run the Automated API Test Suite

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_api_health.py tests/test_api_auth.py tests/test_api_daily_logs.py tests/test_api_audio.py -v
```

These tests use SQLite in-memory (via `tests/conftest_api.py`) — **no PostgreSQL connection required**. They build a fully isolated app instance per test via `create_app(settings=test_settings)`.

Run the entire project's test suite (Sprints 1–7 combined):
```powershell
.\venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: `777 passed, 1 skipped`.

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `RuntimeError: DATABASE_URL environment variable is not set` on server start | `.env` not found/loaded | Confirm `.env` exists in the project root (same directory you run `uvicorn` from) and contains `DATABASE_URL=...`. `app/main.py` calls `load_dotenv()` which looks for `.env` in the current working directory. |
| `password authentication failed for user "postgres"` | Wrong password in `.env`, or `alembic` CLI using its `alembic.ini` fallback instead of `.env` | For the app itself: fix `DATABASE_URL` in `.env`. For direct `alembic` CLI commands: see the gotcha note in step 3. |
| `/api/v1/health` shows `groq_extraction_engine: "down"` | Missing/invalid `GROQ_API_KEY`, or no internet connectivity | Check `.env`, confirm the key is valid at console.groq.com. |
| `401 Unauthorized` on every protected endpoint even with a token | Token expired (default: 60 minutes), or signed with a different `JWT_SECRET_KEY` than the one the running server is using | Log in again for a fresh token. If you changed `JWT_SECRET_KEY` in `.env`, restart the server — `Settings` is cached per-process. |
| `POST /api/v1/auth/login` always returns 401 for the dev admin | `ensure_dev_admin_password()` was never run, or ran before `seed_sample_data()` created the row | Run `python -m app.core.dev_seed` (step 4) — it's idempotent, safe to re-run. |
| `only one usage of each socket address is normally permitted` on server start | A previous uvicorn process is still bound to port 8000 | Find and stop it: `Get-NetTCPConnection -LocalPort 8000 -State Listen \| Select OwningProcess`, then `Stop-Process -Id <pid> -Force`. |
| Alembic reports a different head than expected | Migration files out of sync with what's applied | `python -m alembic current` shows what's applied; `python -m alembic heads` shows what the code defines. They should match (`001`). |

---

## 11. Stopping the Server

`Ctrl+C` in the terminal running uvicorn triggers a graceful shutdown — the `_lifespan` context manager in `app/create_app.py` logs a shutdown message; no explicit cleanup is currently registered there (the database connection pool is process-lifetime and closes when the process exits).
