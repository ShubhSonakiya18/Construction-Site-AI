# End-to-End Testing (Playwright)

**Sprint 18.** `frontend/e2e/` is the first real, checked-in E2E suite this project has had. `@playwright/test` has been an installed dependency since Sprint 9, but every "verified live in a real Playwright browser session" claim across Sprints 9 through 17 was actually run through a fresh, throwaway script written for that sprint alone — never a re-runnable, version-controlled suite. This document exists so that stops being true going forward.

---

## Prerequisites

The suite drives the **real, already-running** application — it does not start either server itself (see `frontend/playwright.config.ts`'s comment on why there's no `webServer` block). Before running it:

1. The real backend, per `docs/BACKEND_STARTUP.md` steps 1-5 — PostgreSQL, migrations + seed data, Redis + Celery worker, and `uvicorn app.main:app` on `127.0.0.1:8000`.
2. The real frontend dev server: `cd frontend && npm run dev` (Vite, `http://localhost:5173`).
3. `npx playwright install chromium` once, if browsers aren't already downloaded (`%LOCALAPPDATA%\ms-playwright` on Windows).

This mirrors the precondition every prior manual verification session in this project's history has always had — a real backend and a real frontend already up, per `docs/BACKEND_STARTUP.md`.

## Running the suite

```powershell
cd frontend
npm run test:e2e
```

Runs headless by default. Add `--headed` to watch it, or `--debug` to step through a single spec.

## What's covered

- `e2e/auth.spec.ts` — unauthenticated redirect to `/login`, successful login, invalid-credentials error, logout.
- `e2e/dashboard-and-log-review.spec.ts` — project picker, daily log list, opening a log into the review page, the grounded Q&A box (a real Groq call — this spec has a longer `expect()` timeout to match).
- `e2e/record-page.spec.ts` — the Record page loads and shows the recording control for an upload-permitted role. Does **not** exercise real microphone capture — headless Chromium has no real microphone, and every prior manual verification of this page stopped at the same boundary (page loads, button present).
- `e2e/client-role-curation.spec.ts` — the staff-only analytics curation check Sprint 13 (ADR-056) established and Sprints 14, 15, and 17 each manually re-verified by hand. No `client`-role user exists in the seed data (`database/seed/sample_data.py` seeds only an `owner`), so this spec creates one via a real `POST /api/v1/users` call in `beforeAll`, the same thing every prior sprint's manual verification did by hand. The created user is not cleaned up afterward (this codebase has no user-deletion endpoint — only deactivation — and a throwaway dev-database e2e user is harmless); re-running the suite against a shared, long-lived database will accumulate `e2e-client-<timestamp>@example.com` rows over time, which is an accepted tradeoff for a local/dev-only suite, not something intended for a shared staging environment as-is.

## Extending it

Per `docs/CONTRIBUTING.md` §9: a UI-facing change should extend `frontend/e2e/` with a real spec, the same way a backend change must extend the real `tests/` suite rather than a one-off script. Reach for a fresh, uncommitted script only for something genuinely exploratory that isn't going to be re-run — not as the default way to "verify it live."

## Known limitations

- Single browser project (Chromium) — no cross-browser matrix. Not attempted this sprint; add further `projects` entries in `playwright.config.ts` if cross-browser coverage becomes a real requirement.
- Not wired into CI — there is no CI pipeline in this repository at all yet (backend or frontend). Out of scope for Sprint 18; see `docs/DECISIONS.md`'s Pending Decisions table.
