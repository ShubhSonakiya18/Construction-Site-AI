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

Builds all 28 tables (+ `alembic_version`) if they don't already exist. **This
step and step 4 do NOT go through `app/main.py`, so `.env` is never
auto-loaded for them** — set `DATABASE_URL` in the shell first, in the exact
same PowerShell session you'll run `alembic`/`dev_seed` in:

```powershell
$env:DATABASE_URL = "postgresql://postgres:<password>@localhost:5432/construction_site_ai"
.\venv\Scripts\python.exe -m alembic upgrade head
```

Verify:
```powershell
.\venv\Scripts\python.exe -m alembic current
```
Expect `004 (head)` (four migrations: `001_initial_schema`, `002_user_sessions`,
`003_account_lockout`, `004_audit_log_structured_fields`).

> **Known gotcha:** running `alembic` directly (or with `DATABASE_URL` unset in
> the shell) silently reads `alembic.ini`'s fallback `sqlalchemy.url` (a
> placeholder, wrong password) instead of your real `.env` — it does NOT error
> out and tell you it fell back. If you see a password-authentication error
> here, this is almost always why. Setting `DATABASE_URL` in the shell, as
> shown above, is the fix — there is no way to make plain `alembic upgrade
> head` (with no env var set) read `.env` automatically, because `.env`
> loading is `app/main.py`'s job, not Alembic's.

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

## 4.5. Start Redis and the Celery Worker (Sprint 9)

The audio pipeline (`POST /audio/upload`) now runs on Celery instead of
FastAPI's `BackgroundTasks` — a Celery worker process must be running or
uploads will accept (202) but never process (stuck in `"pending"` forever).

**Redis** (broker + result backend). This project runs it via Docker rather
than a native Windows install:
```powershell
docker run -d --name construction-redis -p 6379:6379 --restart unless-stopped redis:7-alpine
```
If the container already exists from a previous session: `docker start construction-redis`.

Verify:
```powershell
docker exec construction-redis redis-cli ping
```
Expect `PONG`.

**Celery worker** — in its own terminal, left running (like uvicorn):
```powershell
.\venv\Scripts\celery.exe -A celery_app worker --loglevel=info --pool=solo
```
`--pool=solo` is required on Windows — Celery's default prefork pool uses
`os.fork()`, which Windows does not support.

Expect:
```
[tasks]
  . app.tasks.pipeline_tasks.run_pipeline_task

[...] celery@<hostname> ready.
```

Like Alembic and `dev_seed` (§3–4), this process does **not** go through
`app/main.py` — `celery_app.py` calls `load_dotenv()` itself, so `.env` is
picked up automatically. No manual `$env:` export needed here.

> **Known gotcha:** if you edit `.env` (e.g. change `CELERY_BROKER_URL`),
> the worker does not pick it up on its own — like the FastAPI server (§5),
> it must be fully stopped (`Ctrl+C`) and restarted, not relied upon to
> hot-reload.

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
Expected: `997 passed, 0 skipped` (backend). Frontend: `cd frontend && npm run test` — expect `66 passed`.

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `RuntimeError: DATABASE_URL environment variable is not set` on server start | `.env` not found/loaded | Confirm `.env` exists in the project root (same directory you run `uvicorn` from) and contains `DATABASE_URL=...`. `app/main.py` calls `load_dotenv()` which looks for `.env` in the current working directory. |
| `password authentication failed for user "postgres"` | Wrong password in `.env`, or `alembic` CLI using its `alembic.ini` fallback instead of `.env` | For the app itself: fix `DATABASE_URL` in `.env`. For direct `alembic` CLI commands: see the gotcha note in step 3. |
| `/api/v1/health` shows `groq_extraction_engine: "down"` | Missing/invalid `GROQ_API_KEY`, or no internet connectivity | Check `.env`, confirm the key is valid at console.groq.com. |
| `401 Unauthorized` on every protected endpoint even with a token | Token expired (default: 60 minutes), or signed with a different `JWT_SECRET_KEY` than the one the running server is using | Log in again for a fresh token. If you changed `JWT_SECRET_KEY` in `.env`, restart the server — `Settings` is cached per-process. |
| `POST /api/v1/auth/login` always returns 401 for the dev admin | `ensure_dev_admin_password()` was never run, or ran before `seed_sample_data()` created the row | Run `python -m app.core.dev_seed` (step 4) — it's idempotent, safe to re-run. |
| `only one usage of each socket address is normally permitted`, or `[WinError 10013] An attempt was made to access a socket in a way forbidden by its access permissions`, on server start | Same root cause behind two different Windows error messages: a previous uvicorn process (often left running from an earlier terminal session that was closed without `Ctrl+C`) is still bound to port 8000. `10013` looks like a permissions/firewall error but almost always is not — it is what Windows reports when a port is already held. | Find and stop it: `Get-NetTCPConnection -LocalPort 8000 -State Listen \| Select OwningProcess`, then `Stop-Process -Id <pid> -Force`. Then re-run the `uvicorn` command. |
| Alembic reports a different head than expected | Migration files out of sync with what's applied | `python -m alembic current` shows what's applied; `python -m alembic heads` shows what the code defines. They should match (`004`). |
| `POST /audio/upload` returns 202 but `processing_status` stays `"pending"` forever | No Celery worker running, or it can't reach Redis | Confirm `docker exec construction-redis redis-cli ping` returns `PONG`, and that a `celery -A celery_app worker` process is running (§4.5) — check its terminal for `celery@<hostname> ready.` |
| Frontend shows "Could not reach the server" on every page | Backend not running, or frontend started without the Vite proxy picking it up | Confirm `http://127.0.0.1:8000/api/v1/health/live` responds directly; restart `npm run dev` inside `frontend/` after confirming the backend is up. |

---

## 11. Start the Frontend (Sprint 9)

```powershell
cd frontend
npm install    # first time only
npm run dev
```

Opens at `http://localhost:5173`. Requires the backend (§5) to already be
running — `vite.config.ts` proxies `/api/*` to `http://127.0.0.1:8000`. See
`frontend/README.md` for the frontend's own structure and testing notes.

---

## 12. Stopping Everything

- **Frontend / FastAPI / Celery worker:** `Ctrl+C` in each terminal triggers a graceful shutdown. FastAPI's `_lifespan` context manager (`app/create_app.py`) logs a shutdown message; no explicit cleanup is registered there (the database connection pool is process-lifetime and closes when the process exits).
- **Redis:** `docker stop construction-redis` (data persists in the container; `docker rm construction-redis` to remove it entirely, losing any queued/unacknowledged Celery tasks and rate-limit counters).
