# Construction Site AI — Frontend

Sprint 9 React frontend core: login/logout, project dashboard (daily-log
list + grounded Q&A), voice recording + pipeline status, and daily-log
review (approve/reject).

Vite + React + TypeScript, no additional state library — auth state lives
in `src/auth/AuthContext.tsx` (React Context), everything else is
component-local `useState`, matching the app's current size.

## Prerequisites

The backend must be running first — see `../docs/BACKEND_STARTUP.md` for
the full sequence (PostgreSQL, Redis, Celery worker, FastAPI). This
frontend expects it at `http://127.0.0.1:8000`.

## Running

```bash
npm install
npm run dev
```

Opens at `http://localhost:5173`. `vite.config.ts` proxies `/api/*` to the
backend, so the browser never makes a cross-origin request in dev.

## Structure

```
src/
├── api/
│   ├── types.ts       Types mirroring app/schemas/*.py — kept in
│   │                  lockstep by hand, no codegen step yet.
│   ├── client.ts       axios instance: attaches the access token,
│   │                  transparently refreshes on 401 (single in-flight
│   │                  refresh shared across concurrent 401s — see its
│   │                  docstring for why that matters given Sprint 8's
│   │                  refresh-token rotation).
│   └── endpoints.ts    One typed function per backend endpoint used.
├── auth/
│   └── AuthContext.tsx Login state, exposed via useAuth().
├── components/
│   ├── ProtectedRoute.tsx  Redirects to /login if not authenticated.
│   └── AppLayout.tsx       Header/nav shell for authenticated routes.
└── pages/
    ├── LoginPage.tsx
    ├── ForgotPasswordPage.tsx
    ├── ResetPasswordPage.tsx    Consumes ?token= from the emailed link
    │                            (see app/services/auth_service.py's
    │                            forgot_password()).
    ├── DashboardPage.tsx        Daily-log list + grounded Q&A
    │                            (POST /projects/{id}/ask, ADR-042).
    ├── LogReviewPage.tsx        Full log detail + approve/reject.
    └── RecordPage.tsx           MediaRecorder capture -> upload ->
                                 poll GET /audio/{id}/status.
```

## Known gap: no project picker

There is no `GET /projects` (list) endpoint in the backend yet — full
project CRUD is explicitly deferred (see `../docs/NEXT_SPRINT.md`). The
Dashboard therefore takes a project ID typed in directly (persisted in
`localStorage`) rather than a dropdown. Update `DashboardPage.tsx` once
that endpoint exists.

## Testing this frontend

No component test suite yet (Jest/Vitest + Testing Library, per
`../docs/NEXT_SPRINT.md` Deliverable 5, is a follow-up). This build was
verified with a real Playwright-driven browser session against the real
running backend — login, dashboard, log review, grounded Q&A, recording
page, and logout all confirmed working with zero console errors and zero
failed API requests.
