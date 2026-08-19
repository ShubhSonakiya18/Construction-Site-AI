# Project Pause — Handoff Notes (2026-08-19)

Read this first when picking the project back up. It captures exactly
where things stand, what was just verified working, and what to do next.

---

## 1. Current state — everything verified working

As of this pause, the full verification sweep passed clean:

| Check | Result |
|---|---|
| Backend test suite (`python -m pytest -q`) | **997 passed** |
| Frontend test suite (`npm run test` in `frontend/`) | **73 passed** (11 files) |
| Frontend typecheck (`npx tsc -b`) | Clean, 0 errors |
| Frontend production build (`npm run build`) | Succeeds |
| Live browser verification (RecordPage upload flow) | Confirmed via Playwright + manual testing |
| Live mp4 upload through the real pipeline | Confirmed — reached the daily-log-creation stage |

Sprint 10 is **complete, code-verified, but still marked PENDING APPROVAL**
in `docs/PROJECT_STATE.md` — no explicit approval instruction was given for
it before this pause. Approve it (update `PROJECT_STATE.md` + `CHANGELOG.md`
the same way Sprint 8/9 were approved) before starting Sprint 11 work, or
decide you want it re-reviewed first.

Sprint 11 spec (Scheduling Module, 7 deliverables) is written in
`docs/NEXT_SPRINT.md` but **not started**.

---

## 2. What changed in this final session (uncommitted at time of writing)

All of this is implemented and verified, but not yet committed — see §5.

1. **RecordPage file upload** (`frontend/src/pages/RecordPage.tsx`) — the
   voice recording page previously only supported live microphone capture.
   Added a file-picker alternative ("Upload a recording" button) that
   converges on the same review/upload UI the microphone path already used.
2. **RecordPage drag-and-drop** — the same page's idle state is now wrapped
   in a dropzone (`.record-dropzone` in `frontend/src/index.css`) that
   accepts a dragged-and-dropped audio file via the same validation path
   (`acceptFile()` helper) as the file picker.
3. **9 new/updated tests** in `frontend/src/pages/RecordPage.test.tsx`
   covering both the file-picker and drag-and-drop paths (valid file,
   invalid extension, discard, upload call correctness).
4. **ffmpeg installed on this machine** via `winget install ffmpeg` — fixes
   MP4/M4A audio uploads, which previously failed processing with
   `"Cannot read audio data from '<file>'"` even though the upload itself
   succeeded. Root cause: `speech/loaders/audio_loader.py` falls back to
   `librosa` for formats `soundfile` can't read natively (MP3/M4A/MP4),
   and librosa's fallback decoder shells out to ffmpeg — which wasn't
   installed. **No application code changed for this fix** — it was purely
   a missing system dependency, now documented as a prerequisite.
5. **`docs/BACKEND_STARTUP.md`** updated: ffmpeg added to §1 Prerequisites,
   plus a new troubleshooting row for the "Cannot read audio data" symptom.

### A real Windows gotcha hit and resolved during this session

Installing ffmpeg via winget updates the registry PATH, but:
- Already-running terminals/processes don't see it (expected).
- **New** terminals didn't see it either at first, because `explorer.exe`
  caches the environment block and only refreshes it on logoff/logon or a
  restart of `explorer.exe` itself — just opening a "new" terminal window
  is not enough on Windows.
- Fixed by restarting `explorer.exe` (`Stop-Process -Name explorer -Force`
  then `Start-Process explorer`), which was enough for a genuinely new
  terminal to finally see ffmpeg on PATH.
- Two duplicate/stale Celery worker processes (one from 3:15 AM, one from
  8:12 AM — both predating the ffmpeg install in terms of inherited PATH)
  were found and stopped so a fresh worker could take over.

**If you ever reinstall or update ffmpeg (or any winget package) again and
new terminals still don't see it on PATH, try the `explorer.exe` restart
trick before assuming something is broken.**

---

## 3. Known non-blocking items (not bugs, just things to be aware of)

- **One daily log per project per day is enforced by design** (a Sprint
  7/8 guard against silently overwriting a day's log). During this
  session's live mp4 test, a second upload against the same project on the
  same day was correctly rejected with `"A daily log already exists for
  this project on <date>... Upload rejected to avoid overwriting it."`
  This is not a bug — do not weaken this guard casually. If multiple
  daily logs per project per day becomes a real product requirement
  (e.g. multiple foremen filing separately), that needs a deliberate
  schema/business-logic decision, not a quick patch.
- Only one project is seeded in dev data
  (`aaaaaaaa-0006-4000-8000-000000000006`, from
  `database/seed/sample_data.py`). For repeated manual testing that hits
  the per-day guard, either leave the Project ID field blank on upload
  (the guard only applies when a project_id is given) or seed a second
  project.
- The frontend production bundle is a single ~682KB JS chunk (206KB
  gzipped) — Vite warns about this. Not a regression from this session;
  pre-existing. Worth code-splitting eventually (dynamic `import()`) but
  not urgent.

---

## 4. Next steps when resuming

In rough priority order:

1. **Decide on Sprint 10 approval.** It's fully built and verified; either
   formally approve it (update `docs/PROJECT_STATE.md`,
   `docs/CHANGELOG.md`, mark FROZEN like Sprints 1-9) or flag anything
   you want changed first.
2. **Commit and push the uncommitted work from §2** (see §5 for what's
   staged and ready).
3. **Start Sprint 11 — Scheduling Module**, spec already written in
   `docs/NEXT_SPRINT.md` (7 deliverables, grounded in
   `knowledge/dependency_graph.json`'s 23 nodes / 33 edges / 97-day
   critical path — confirmed no production Schedule/Task table exists yet).
4. Consider whether the manager-facing progress-report artifact should be
   refreshed to include Sprint 10 + this session's fixes — the existing
   one (published at the URL noted in project memory) only covers through
   Sprint 10 at a high level and predates this session's bug fixes.

---

## 5. To restart the project from scratch

Follow `docs/BACKEND_STARTUP.md` end to end — it now includes the ffmpeg
prerequisite. Quick summary:

1. Start PostgreSQL, Redis (Docker), and confirm `.env` has
   `DATABASE_URL` / `GROQ_API_KEY`.
2. `python -m alembic upgrade head`
3. `python -m app.core.dev_seed` (idempotent)
4. **New terminal** → confirm `ffmpeg -version` resolves → start Celery
   worker: `celery -A celery_app worker --pool=solo`
5. Start FastAPI: `uvicorn app.main:app --reload`
6. Start frontend: `cd frontend && npm run dev`
7. Log in at `http://localhost:5173` with `admin@example.com` /
   `Admin@123`.
