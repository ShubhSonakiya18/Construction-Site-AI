# Next Sprint: Sprint 18 — Playwright E2E Suite and a Real requirements.txt

**Status:** READY TO BEGIN — Sprint 17 approved 2026-09-17 (see `docs/PROJECT_STATE.md`).
**Prerequisites:** Sprint 17 APPROVED and FROZEN — satisfied. PostgreSQL, Redis, and a running Celery worker (Sprint 9 requirements) still apply.

---

## Sprint 18 Goal

Both nominal Phase 5 roadmap items (Defect Detection, Bid Estimation) were re-checked before scoping this sprint and remain exactly as blocked as Sprint 17 found them — the database still has exactly one project, and no photo-upload/vision-model infrastructure has appeared. Rather than force either premise, this sprint closes real, previously-identified process gaps instead: `docs/RESUME_AUDIT_2026-09-15.md` (written during the September resume) flagged two tooling gaps that no sprint since has touched:

- **§12 (P3): no `requirements.txt` exists, only `requirements-dev.txt`.** Confirmed still true — `requirements-dev.txt` (31 packages) mixes real runtime dependencies (`fastapi`, `sqlalchemy`, `groq`, `celery`, `reportlab`, etc.) with dev/test-only tooling (`pytest`, `pytest-cov`, `pytest-asyncio`, `faker`, `tqdm`) with no separation. A production install has no way to skip the ~5 packages it will never use.
- **§12 (P3) / Sprint 10's own audit note: `@playwright/test` is installed but was never wired up.** Confirmed still true today — `frontend/package.json`'s `devDependencies` includes `@playwright/test` and its `scripts` block has `dev`/`build`/`lint`/`preview`/`test` but no `test:e2e`; there is no `playwright.config.ts` and no `e2e/` directory anywhere in `frontend/`. Every "verified live in a real Playwright browser session" claim across Sprints 9 through 17 — and there have been many, this project's core verification discipline — was actually run through a one-off script written fresh each time, not a real, re-runnable, checked-in test suite. This is real, accumulated process debt: the same login → navigate → assert flow has been hand-written from scratch more than a dozen times.

**A third candidate, Docker Compose (a one-command local stack), was investigated and explicitly descoped for this sprint** — the development machine's C: drive currently has 0 bytes free, and pulling/building the images a real `docker-compose up` needs (Postgres, Redis, the backend image, at minimum) is not possible until disk space is freed. Writing Docker config files without being able to run them would violate this project's own live-verification discipline (ADR/CONTRIBUTING §5's standing rule against claiming something works without proving it), so Docker Compose is deferred to a future sprint rather than attempted half-verified. See `docs/DECISIONS.md`'s Pending Decisions table, which already carries "Docker multi-stage build | Sprint 10+ | Open" — this sprint does not resolve that row.

**What this means for scope:** both deliverables are pure tooling/process work, fully live-verifiable within normal disk constraints (no new heavyweight dependencies, no Docker), and both directly address debt this project's own audit discipline already named and tracked but never scheduled.

What already exists and should NOT be rebuilt:
- `requirements-dev.txt` — stays as the complete dev/test manifest (CI and local dev still install from it); this sprint adds a second, smaller file alongside it, it does not replace or restructure the existing one.
- `@playwright/test` itself — already the correct, already-installed dependency; this sprint configures and uses it, it does not swap in a different E2E framework.
- Every real user flow this sprint's E2E suite covers (login, dashboard, record page, log review, analytics) — already real, working, manually-verified functionality from Sprints 9-17. This sprint automates verification of what already works, it does not change any product behavior.

---

## Deliverables

### 1. `requirements.txt` — Runtime-Only Dependency Manifest

- New file at the repo root, alongside `requirements-dev.txt`. Contains only the packages the running application actually imports at runtime — every package in `requirements-dev.txt` except the dev/test-only ones (`pytest`, `pytest-cov`, `pytest-asyncio`, `faker`, `tqdm` — confirmed by checking each package's own section header/comment in `requirements-dev.txt`, not guessed).
- Verify by installing into a clean virtual environment and confirming `uvicorn app.main:app` starts successfully and `GET /api/v1/health` returns 200 — a real proof the runtime manifest is complete, not just a visual diff against the dev file.
- `docs/BACKEND_STARTUP.md`'s prerequisites section gets a one-line update noting `requirements.txt` is the production/runtime manifest and `requirements-dev.txt` (which already includes everything in it, plus test tooling) is what local development actually installs from — no change to the actual setup instructions, which continue to reference `requirements-dev.txt`.

### 2. Wire Up Playwright as a Real, Re-Runnable E2E Suite

- `frontend/playwright.config.ts` — base URL pointing at the Vite dev server (`http://localhost:5173`), a reasonable default timeout, and screenshot-on-failure (useful for exactly the kind of visual regression this project's live-verification discipline already cares about).
- `frontend/e2e/` directory with real spec files codifying the flows that have actually been manually verified, repeatedly, across this project's history — not new flows invented for this sprint:
  - Login → Dashboard (redirect-when-unauthenticated, successful login, logout)
  - Dashboard → project picker → daily log list → log review page (trades/work items/Approve-Reject visible for an owner-role user)
  - RecordPage loads and shows the recording UI (not exercising real microphone capture — every prior verification of this page has stopped at "the page loads and the button is present" for the same reason: headless browsers don't have a real microphone)
  - AnalyticsPanel renders its sections for a staff role and hides staff-only sections for a client role — directly automating the client-role curation check Sprint 13 (ADR-056) and every cost/safety-related sprint since has manually re-run by hand
- `frontend/package.json` gains a real `test:e2e` script (`playwright test`). Document in `docs/BACKEND_STARTUP.md` (or a new short `docs/E2E_TESTING.md`, decide during implementation which reads better) that the suite needs the real backend + frontend dev servers already running — it drives the real app, it does not spin up its own.
- Live-verify by actually running `npm run test:e2e` against the real running stack and confirming it passes — this sprint's own deliverable must survive the same bar every other sprint's frontend work has been held to.

### 3. Retire (or Clearly Mark) Ad-Hoc Verification Scripts Going Forward

- No historical scripts need to be hunted down and deleted (they were scratch work, not committed artifacts, per this project's established scratchpad discipline) — but from this sprint forward, `docs/CONTRIBUTING.md` §9 ("How To Write Tests") gets a short addition: a UI-facing change should extend `frontend/e2e/` rather than a fresh one-off script, the same way a backend change already must extend the real `tests/` suite rather than a throwaway script. This closes the actual gap (the suite existing and being the default, not merely existing).

---

## Constraints

- **No paid APIs, no paid SaaS, no new product features.** This sprint is entirely process/tooling — dependency manifest hygiene and test infrastructure, not a change to what the application does.
- **Sprint 1–17 FROZEN.** `frontend/e2e/` and `requirements.txt` are new, additive files; no existing application code changes except the one-line `docs/BACKEND_STARTUP.md` note and the `docs/CONTRIBUTING.md` addition.
- **No Docker.** Explicitly descoped this sprint due to the disk-space constraint — see the Goal section. Do not write a Dockerfile or docker-compose.yml as an unverified bonus; an unrun, unverified artifact contradicts this project's own discipline more than not writing it at all.
- **Continue the "explain, implement, test, verify" per-subsystem discipline**, live verification over assumption — `requirements.txt` must be proven by a real clean-venv install and a real server start, not eyeballed; the E2E suite must be proven by actually running it against the real stack, not just committing config files that were never executed.

---

## Explicit Out of Scope for Sprint 18

- Docker Compose / a Dockerfile / any containerization — blocked on disk space; remains an Open row in `docs/DECISIONS.md`'s Pending Decisions table for a future sprint once space is available.
- CI/CD (`.github/workflows` or similar) running either suite automatically — this sprint makes the E2E suite runnable and real; wiring it into a CI pipeline is a distinct, separately-scoped decision (there is no CI today at all, backend or frontend).
- Any new product feature, including further Phase 5 investigation — both nominal items remain blocked exactly as Sprint 17 found them; nothing here changes that.
- Testing real microphone/audio-recording capture through Playwright — headless browsers have no real microphone, and every prior manual verification of `RecordPage.tsx` has stopped at the same boundary (page loads, button present) for the same reason. Not attempted here either.
- A notification/alerting scheduler or persisted AI usage metrics — both real, investigated candidates for future sprints (see the Sprint 18 scoping discussion in `docs/PROJECT_STATE.md`), not this sprint's chosen focus.
