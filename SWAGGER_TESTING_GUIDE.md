# Swagger UI Testing Guide — Construction Site AI API

**Written for someone with zero FastAPI/Swagger experience.** Follow this top to bottom, in order — later steps depend on IDs and tokens you get from earlier ones. Every ID and expected output below is real, taken from this project's actual seeded data.

---

## Before You Start

### 1. Start the server

Open a terminal (PowerShell), go to the project folder, and run:
```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Wait until you see:
```
INFO:     Application startup complete.
```

**Leave this window open and running.** Don't close it, don't press Ctrl+C, don't type anything else in it. If you need to run more commands, open a **second** terminal window.

### 2. Open Swagger UI

In your browser, go to: **http://127.0.0.1:8000/docs**

This is the page in your screenshots — a list of all endpoints grouped by category (Health, Auth, Audio, Daily Logs, Projects).

### 3. How "Try it out" works (same for every endpoint)

For every endpoint below, the pattern is always the same 4 clicks:
1. Click the endpoint's blue/green bar to expand it
2. Click the **"Try it out"** button (top right of the expanded section)
3. Fill in any required fields
4. Click the blue **"Execute"** button
5. Scroll down to **"Server response"** → **"Response body"** to see what came back

---

## Part 1 — Health Endpoints (no login needed)

These have no lock icon 🔓 — you can test them immediately, before logging in.

### 1.1 `GET /api/v1/health/live`

**What it checks:** is the server process even running? No database, no external calls — the fastest, simplest check.

**Steps:**
1. Click `GET /api/v1/health/live`
2. Try it out → Execute (no inputs needed)

**Expected response — Code `200`:**
```json
{
  "success": true,
  "message": "Process is alive.",
  "data": { "status": "alive", "uptime_seconds": 12.3 },
  ...
}
```

If you get this, the server is up. If you get a connection error instead, your `uvicorn` terminal isn't running — go back to step 1 above.

---

### 1.2 `GET /api/v1/health/ready`

**What it checks:** can the server actually reach the PostgreSQL database?

**Steps:** Same as above — Try it out → Execute.

**Expected response — Code `200`:**
```json
{
  "success": true,
  "message": "Ready.",
  "data": { "status": "ready", "database": true }
}
```

If `"database": false`, PostgreSQL isn't running or your `.env` has the wrong connection details.

---

### 1.3 `GET /api/v1/health/version`

**What it checks:** what version/environment is running. No I/O at all.

**Expected response — Code `200`:**
```json
{
  "data": { "app_version": "0.7.0", "environment": "development", "api_version": "v1" }
}
```

---

### 1.4 `GET /api/v1/health` (the full one)

**What it checks:** database **and** the Groq AI engine — this is the "everything OK?" check. Takes ~1 second longer than the others because it makes a real call to Groq.

**Expected response — Code `200`:**
```json
{
  "data": {
    "status": "up",
    "components": {
      "database": { "status": "up" },
      "groq_extraction_engine": { "status": "up" }
    }
  }
}
```

If `groq_extraction_engine` shows `"down"`, check your `.env` has a valid `GROQ_API_KEY`.

---

## Part 2 — Authentication

You now need to log in. Every endpoint below this point has a 🔒 lock icon — it needs a token.

### 2.1 `POST /api/v1/auth/login`

**Steps:**
1. Click `POST /api/v1/auth/login` under "Auth"
2. Try it out
3. In the **Request body** box, replace the placeholder text with exactly:
```json
{
  "email": "admin@example.com",
  "password": "Admin@123"
}
```
4. Execute

**Expected response — Code `200`:**
```json
{
  "success": true,
  "message": "Login successful.",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...(long string)...",
    "token_type": "bearer",
    "expires_in_minutes": 60,
    "role": "owner",
    "email": "admin@example.com"
  }
}
```

**Copy the entire `access_token` value** (everything between the quotes, starting with `eyJ...`) — you need it for the next step. Click inside the response box and select/copy just that string.

> This is the one working demo login built into the project. `admin@example.com` / `Admin@123` is intentional test data, not something you need to create yourself.

**Now test the failure case too**, so you know what "wrong password" looks like:
- Try it out again → body: `{"email": "admin@example.com", "password": "wrongpassword"}` → Execute
- **Expected: Code `401`**, body: `{"success": false, "message": "Incorrect email or password."}`

---

### 2.2 Authorize Swagger with your token

This is the step that unlocks every other endpoint — **do this once, then it applies to every request you make for the rest of the session.**

1. Scroll to the **top** of the Swagger page
2. Click the green **"Authorize" 🔒** button (visible in your first screenshot, top right)
3. A popup appears with a field labeled something like `HTTPBearer (http, Bearer)`
4. Paste your `access_token` value in — **just the raw token, do NOT type "Bearer" in front of it**, Swagger adds that automatically
5. Click **Authorize**, then **Close**

Every lock icon 🔒 next to the endpoints should now look "closed"/active — you're authenticated for the rest of this session.

---

## Part 3 — Daily Logs (CRUD + review lifecycle)

Use this real, pre-existing daily log ID for everything in this section:
```
aaaaaaaa-0008-4000-8000-000000000008
```

### 3.1 `GET /api/v1/daily-logs/{log_id}`

**Steps:**
1. Click `GET /api/v1/daily-logs/{log_id}` under "Daily Logs"
2. Try it out
3. In the `log_id` field, paste: `aaaaaaaa-0008-4000-8000-000000000008`
4. Execute

**Expected response — Code `200`:**
```json
{
  "success": true,
  "data": {
    "id": "aaaaaaaa-0008-4000-8000-000000000008",
    "current_stage": "framing",
    "review_status": "approved",
    "total_workers_present": 7,
    "trades_on_site": [ {...}, {...} ],
    "work_items": [ {...}, {...}, {...} ],
    "hazards": [ {...} ],
    ...many more fields...
  }
}
```
This is a full construction daily log with all its nested detail — trades on site, work completed, materials used, safety hazards, etc.

**Now test the error case:**
- Change `log_id` to a fake one: `00000000-0000-0000-0000-000000000000` → Execute
- **Expected: Code `404`**, `{"success": false, "message": "Daily log not found."}`

- Change `log_id` to garbage text: `not-a-real-id` → Execute
- **Expected: Code `422`** (validation error — it's not even a valid UUID shape)

---

### 3.2 The review lifecycle is a strict state machine — understand this before testing 3.2-3.4

The three endpoints below (`submit`, `approve`, `reject`) only allow specific transitions. Trying an invalid one is **supposed to fail with `409 Conflict`** — that's the state machine correctly protecting the workflow, not a bug:

```
draft ──submit──▶ under_review ──approve──▶ approved
                       │
                       └──reject──▶ rejected
```

| Action | Allowed FROM status | Result |
|---|---|---|
| `submit` | `draft` | → `under_review` |
| `approve` | `draft` **or** `under_review` | → `approved` |
| `reject` | `under_review` (implementation also allows any status except the immutable ones — but always test from `under_review`) | → `rejected` |

**Key rule that trips people up:** `approve` does **NOT** accept a log that is already `approved` or `rejected` as input. If you call `approve` on a log that's already `approved`, you get `409`:
```json
{ "message": "Cannot approve log ...: current status is 'approved'" }
```
That is correct, expected behavior — not something to "fix." The seeded sample log (`aaaaaaaa-0008-...`) starts out `approved`, so if you try `submit` or `approve` on it directly, you'll hit a `409` immediately. That's why the walkthrough below starts by resetting it to `draft` first.

---

### 3.2a Check the log's current status before testing

**Steps:**
1. `GET /api/v1/daily-logs/{log_id}` → `log_id`: `aaaaaaaa-0008-4000-8000-000000000008` → Execute
2. Look at the `review_status` field in the response.

- If it says `"draft"` → skip ahead to **3.2b Submit** below.
- If it says `"under_review"` → skip ahead to **3.3 Approve** below.
- If it says `"approved"` or `"rejected"` → you'll need to reset it to `draft` before continuing (see the box below), because there is no API call that moves a log backward — that's intentional, review decisions are meant to be final and auditable, not casually undone.

> **If you need to reset the seeded log back to `draft`:** this requires a direct database update (there's no "unapprove" endpoint — on purpose, so approvals stay auditable). This is a one-time housekeeping step for testing, not something a real user would do. Ask your project maintainer/AI assistant to reset `review_status`, `reviewed_by_id`, `reviewed_at`, and `review_notes` to `draft`/`NULL` for this one row if you need a clean slate.

---

### 3.2b `POST /api/v1/daily-logs/{log_id}/submit`

**What it does:** moves a log from `draft` to `under_review` — the first step in the approval workflow. **Only works if the log is currently `draft`.**

**Steps:**
1. `log_id`: `aaaaaaaa-0008-4000-8000-000000000008` (assuming it's currently `draft` — see 3.2a)
2. Execute (no request body needed)

**Expected response — Code `200`:**
```json
{
  "success": true,
  "message": "Submitted for review.",
  "data": { "review_status": "under_review", "reviewed_by_id": null, "reviewed_at": null, ... }
}
```
*(This is the actual response captured from a real run of this exact call.)*

**If the log is NOT currently `draft`**, you'll correctly get:
```json
{
  "success": false,
  "message": "Cannot submit log aaaaaaaa-0008-4000-8000-000000000008 for review: current status is 'approved' (must be 'draft')"
}
```
— **Code `409`.** This is correct behavior, not an error to fix. It means the log is already further along in the workflow than `draft`.

---

### 3.3 `POST /api/v1/daily-logs/{log_id}/approve`

**What it does:** moves a log from `draft` **or** `under_review` to `approved`. Records who approved it and when.

**Steps:**
1. `log_id`: `aaaaaaaa-0008-4000-8000-000000000008` (should now be `under_review` after 3.2b)
2. Request body:
```json
{ "notes": "Looks good, approving." }
```
3. Execute

**Expected response — Code `200`:**
```json
{
  "success": true,
  "message": "Log approved.",
  "data": {
    "review_status": "approved",
    "review_notes": "Looks good, approving.",
    "reviewed_by_id": "aaaaaaaa-0009-4000-8000-000000000009",
    "reviewed_at": "2026-07-14T15:28:28.220255Z",
    ...
  }
}
```
*(Real captured response — `reviewed_by_id` is the account that made the call, `reviewed_at` is a real server timestamp.)*

**Note:** only `owner` and `project_manager` roles can approve. The `admin@example.com` account has role `owner`, so this works. If you tried this with a `foreman`-role token, you'd get `403 Forbidden`.

**If you try this again right now** (log is already `approved`), you'll correctly get **Code `409`**:
```json
{ "message": "Cannot approve log ...: current status is 'approved'" }
```
This is the exact scenario that looked like an error earlier — it isn't one. Approve is a one-way, one-time transition per review cycle.

---

### 3.4 `POST /api/v1/daily-logs/{log_id}/reject`

**What it does:** moves a log from `under_review` to `rejected`, with required notes explaining why.

To test this cleanly, you'd want a **different** log that's currently `under_review` (since the one above is now `approved`) — or reset the same log to `draft`/`under_review` again first (see 3.2a's reset note).

**Steps:**
1. `log_id`: (a log currently in `under_review` status)
2. Request body — `notes` is **required**, this call fails without it:
```json
{ "notes": "Missing safety documentation, please redo." }
```
3. Execute

**Expected response — Code `200`:**
```json
{ "data": { "review_status": "rejected", "review_notes": "Missing safety documentation, please redo." } }
```

**Test the validation:** try Execute with an empty body `{}` → **Expected: Code `422`** (notes field is required).

---

### 3.5 `POST /api/v1/daily-logs/{log_id}/generate`

**What it does:** runs the real Groq AI to generate all 4 business documents from this log's data. This makes actual calls to the Groq API — takes **10-40 seconds**, don't panic if it looks stuck.

**Steps:**
1. `log_id`: `aaaaaaaa-0008-4000-8000-000000000008`
2. Execute, then **wait**

**Expected response — Code `200`** (after the wait):
```json
{
  "success": true,
  "message": "Generated 4 document(s).",
  "data": {
    "outputs_generated": 4,
    "service_types": ["daily_report", "customer_update", "safety_talk", "material_reminder"]
  }
}
```

---

### 3.6 `GET /api/v1/daily-logs/{log_id}/outputs`

**What it does:** shows you every AI-generated document ever created for this log — a **full history**, not just the latest one.

**Steps:**
1. `log_id`: `aaaaaaaa-0008-4000-8000-000000000008`
2. Execute

**Expected response — Code `200`:**
```json
{
  "message": "Found 4 output(s).",
  "data": [
    { "service_type": "daily_report", "content": "## Daily Site Report\n...(real generated text)..." },
    { "service_type": "customer_update", "content": "Subject: Project Update\n...(real email text)..." },
    { "service_type": "safety_talk", "content": "## Toolbox Talk\n...(real safety briefing)..." },
    { "service_type": "material_reminder", "content": "## Material Reminder\n...(real procurement list)..." }
  ]
}
```
Read through the `content` field of each — this is real AI-written text based on the daily log's actual data (workers, trades, materials, weather).

> **Ran `/generate` (step 3.5) more than once on the same log?** Each run produces 4 *new* documents and adds them alongside the old ones — it does **not** overwrite or replace previous generations. So `Found 4 output(s).` only holds true the first time; run `/generate` five times and `GET /outputs` correctly returns `"Found 20 output(s)."` (5 generations × 4 document types), newest first within each `service_type`. Seeing a count that's a multiple of 4 — not exactly 4 — means the endpoint is working correctly and you've simply called `/generate` more than once. This is intentional: it preserves a full audit history of every AI generation rather than silently discarding earlier versions.

---

## Part 4 — Projects

### 4.1 `GET /api/v1/projects/{project_id}/daily-logs`

Use this real project ID:
```
aaaaaaaa-0006-4000-8000-000000000006
```

**Steps:**
1. `project_id`: `aaaaaaaa-0006-4000-8000-000000000006`
2. Leave other parameters (status, limit, offset) blank/default
3. Execute

**Expected response — Code `200`:**
```json
{
  "success": true,
  "message": "Found 1 log(s).",
  "data": [ { "id": "aaaaaaaa-0008-4000-8000-000000000008", "review_status": "approved", ... } ],
  "metadata": { "total": 1, "limit": 30, "offset": 0, "count": 1 }
}
```

**Try the filter:** set `status` to `draft` → Execute → **Expected: empty list `[]`** (this log isn't a draft).

---

## Part 5 — Audio Upload (the full AI pipeline)

This is the most impressive one — a real `.wav` file goes in, and Whisper transcription → Groq extraction → database save → Groq document generation → database save all happen automatically in the background.

### 5.1 `POST /api/v1/audio/upload`

This is the endpoint from your second screenshot — **this is exactly where the error you hit earlier came from.**

**Steps:**
1. Click `POST /api/v1/audio/upload` under "Audio"
2. Try it out
3. **`file`** field → click **Choose File** → navigate to and select:
   ```
   data\sample_audio\foreman_recording.wav
   ```
   (inside your project folder)
4. **`project_id`** field → **this is critical** — clear out whatever placeholder text is there (it will show something like `3fa85f64-5717-4562-b3fc-2c963f66afa6` — that's Swagger's fake example, it does NOT exist in the database) and type the **real** project ID instead:
   ```
   aaaaaaaa-0006-4000-8000-000000000006
   ```
5. Execute

**Expected response — Code `202`:**
```json
{
  "success": true,
  "message": "Upload accepted. Processing has started.",
  "data": {
    "id": "SOME-NEW-UUID-WILL-APPEAR-HERE",
    "original_filename": "foreman_recording.wav",
    "processing_status": "pending"
  }
}
```

**Copy the `id` value** — you need it for the next step.

> **If you leave `project_id` as the Swagger placeholder UUID**, you'll get a clean `404 Project {id} not found.` — the endpoint checks the project exists before doing anything else. Just replace it with a real project ID to proceed.

---

### 5.2 `GET /api/v1/audio/{audio_file_id}/status`

This is the field your screenshot showed rejecting `foreman_recording.mp4` — that field wants the **UUID from step 5.1's response**, not a filename.

**Steps:**
1. Click `GET /api/v1/audio/{audio_file_id}/status`
2. Try it out
3. Paste the `id` you copied from step 5.1 (looks like `44616efe-b11b-48a4-870e-c28e98e00f9b`)
4. Execute

**Expected response, first try — Code `200`:**
```json
{ "data": { "processing_status": "transcribing", "daily_log_id": null } }
```

**Keep clicking Execute again every few seconds** (Swagger doesn't auto-refresh — you manually re-run it). The status will progress:
```
pending → transcribing → extracting → generating → complete
```
This takes **20-45 seconds total** for a real audio file, since it's really calling Whisper (local) and Groq (cloud) twice.

**Final expected response — Code `200`:**
```json
{
  "data": {
    "processing_status": "complete",
    "daily_log_id": "SOME-NEW-UUID",
    "error_message": null
  }
}
```

Copy that `daily_log_id` — you can now plug it into `GET /api/v1/daily-logs/{log_id}` (Part 3.1) and `GET /api/v1/daily-logs/{log_id}/outputs` (Part 3.6) to see the brand-new log and its 4 freshly-generated documents that came from **your own uploaded recording**, not the seeded sample.

---

### 5.3 What if you upload the same day's recording twice?

If you run 5.1 and 5.2 again on the **same calendar day** for the **same project**, you'll get a clean rejection instead of a crash:

**Expected response — `processing_status: "failed"`:**
```json
{
  "error_message": "A daily log already exists for this project on 2026-07-14 (daily_log_id=...). Upload rejected to avoid overwriting it."
}
```
This is correct, intentional behavior — one log per project per day, and the system tells you exactly which existing log is blocking you.

---

## Quick Reference — All Real IDs Used Above

| What | ID |
|---|---|
| Company | `aaaaaaaa-0001-4000-8000-000000000001` |
| Project | `aaaaaaaa-0006-4000-8000-000000000006` |
| Seeded daily log | `aaaaaaaa-0008-4000-8000-000000000008` |
| Login email | `admin@example.com` |
| Login password | `Admin@123` |

**Never use Swagger's greyed-out placeholder text as a real value** — anywhere you see `3fa85f64-5717-4562-b3fc-2c963f66afa6` or similar pre-filled UUID, that's just an example format, not real data. Always replace it with one of the real IDs above (or one you got back from a previous response, like a new `audio_file_id` or `daily_log_id`).

> The seeded daily log's `review_status` will change as you work through Part 3 below (`approved` → `draft` → `under_review` → `approved`/`rejected`, depending which steps you run). **Always check its current status with `GET /daily-logs/{id}` first** (step 3.2a) rather than assuming it's still in whatever state the seed data started in — the review lifecycle only allows forward transitions, never backward, so testing out of order will correctly produce `409` responses.

---

## Full Test Checklist

Work through in this order — later ones depend on earlier ones:

- [ ] 1.1 `GET /health/live` → `200`
- [ ] 1.2 `GET /health/ready` → `200`, `database: true`
- [ ] 1.3 `GET /health/version` → `200`
- [ ] 1.4 `GET /health` → `200`, both components `up`
- [ ] 2.1 `POST /auth/login` (correct password) → `200`, copy token
- [ ] 2.1b `POST /auth/login` (wrong password) → `401`
- [ ] 2.2 Click Authorize, paste token
- [ ] 3.1 `GET /daily-logs/{id}` (real id) → `200`, full nested data
- [ ] 3.1b `GET /daily-logs/{id}` (fake id) → `404`
- [ ] 3.1c `GET /daily-logs/{id}` (garbage id) → `422`
- [ ] 3.2a Check `review_status` first — confirm it's `draft` before continuing (reset if needed)
- [ ] 3.2b `POST /daily-logs/{id}/submit` (log is `draft`) → `200`, `review_status: under_review`
- [ ] 3.2c `POST /daily-logs/{id}/submit` again (log is now `under_review`) → `409` (expected — can't re-submit)
- [ ] 3.3 `POST /daily-logs/{id}/approve` (log is `under_review`) → `200`, `review_status: approved`
- [ ] 3.3b `POST /daily-logs/{id}/approve` again (log is now `approved`) → `409` (expected — can't re-approve)
- [ ] 3.4 `POST /daily-logs/{id}/reject` (on a log currently `under_review`) → `200`, `review_status: rejected`
- [ ] 3.4b `POST /daily-logs/{id}/reject` (empty body) → `422`
- [ ] 3.5 `POST /daily-logs/{id}/generate` → `200` (wait ~10-40s)
- [ ] 3.6 `GET /daily-logs/{id}/outputs` → `200`, 4 real documents
- [ ] 4.1 `GET /projects/{id}/daily-logs` → `200`, 1 log
- [ ] 5.1 `POST /audio/upload` (real project_id, real file) → `202`
- [ ] 5.2 `GET /audio/{id}/status` (poll until complete) → `200`, `complete`
- [ ] 5.3 (optional) upload same file again same day → clean rejection, not a crash

If every box passes with the expected result, the entire API surface is confirmed working end to end — real database, real AI, real audio pipeline.
