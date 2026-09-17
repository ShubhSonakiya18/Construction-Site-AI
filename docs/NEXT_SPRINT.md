# Next Sprint: Sprint 19 — Proactive Alert Notifications

**Status:** READY TO BEGIN — Sprint 18 approved 2026-09-17 (see `docs/PROJECT_STATE.md`).
**Prerequisites:** Sprint 18 APPROVED and FROZEN — satisfied. PostgreSQL, Redis, and a running Celery worker (Sprint 9 requirements) still apply.

---

## Sprint 19 Goal

Both nominal Phase 5 roadmap items (Defect Detection, Bid Estimation) were re-checked before scoping this sprint and remain exactly as blocked as Sprint 17 found them — still exactly one project in the database, still no photo-upload/vision-model infrastructure. Sprint 18's own scoping discussion surfaced two further real, unblocked candidates that weren't picked up; this sprint takes the first: a real notification/alerting scheduler.

**The gap this closes, precisely.** Two features already compute real, meaningful alert conditions but only ever expose them as a value on a read:

- Sprint 14's `budget_variance.status` (`on_track` / `approaching_budget` / `over_budget` / `no_budget_set`) — computed fresh on every `GET /projects/{id}/analytics`, per `app/services/cost_service.py::compute_budget_variance()`.
- Sprint 15's `safety_proactive_warnings` (unresolved hazards, days since last incident, incidence rate) — computed fresh on every `GET /projects/{id}/analytics`, per `app/services/safety_trend_service.py`.

Both sprints' own "Decided, not built" sections gave the identical reason for stopping at a computed field: *"this codebase has no scheduler or notification infrastructure."* That was true in Sprint 14/15. It is no longer true — Sprint 9 already brought in Celery + Redis for the audio pipeline, and Sprint 9 also already built a real `EmailSender` (`app/services/email_sender.py`, `DevConsoleEmailSender`/`SMTPEmailSender`) for the password-reset flow. **Celery Beat** (a periodic-task scheduler that ships as part of the already-pinned `celery` package — confirmed in `requirements-dev.txt`/`requirements.txt`, no new dependency) is the natural fit: it's the same broker, the same worker process family, the same retry/timeout conventions `celery_app.py` already established, not a second scheduling technology (ruling out APScheduler, which would duplicate infrastructure this project already has for no real benefit).

**What "proactive" has to mean here, concretely:** a periodic Celery Beat task that, for every project with an `on_track`-or-worse budget status or a real safety warning, sends a real email via the existing `EmailSender` to that project's company's relevant staff (owner/admin/project_manager — matching the roles already gated to see this data in `AnalyticsPanel.tsx`'s staff-only sections, ADR-056). This is genuinely new work, not a thin wrapper: computing a value on a read and pushing a value on a schedule are different problems (idempotency/dedup, who to notify, how often to re-notify, what happens across a company with many projects) — the deliverables below scope each honestly.

What already exists and should NOT be rebuilt:
- `app/services/cost_service.py::compute_budget_variance()` / `app/services/safety_trend_service.py` — the alert *conditions* themselves are already correct, tested, and live-verified (Sprint 14/15). This sprint decides when to check them and what to do with a bad result — it does not recompute or re-derive the conditions.
- `app/services/email_sender.py`'s `EmailSender` Protocol/`DevConsoleEmailSender`/`SMTPEmailSender` — real, working, already used by the password-reset flow. This sprint is a second caller of the same interface, not a new email-sending mechanism.
- `celery_app.py` — the Celery application instance, broker/backend config, retry/timeout conventions. This sprint adds a Beat schedule entry and a new periodic task module; it does not touch the existing `app.tasks.pipeline_tasks` audio pipeline task.

---

## Deliverables

### 1. Decide and Document Notification Scope and Dedup Strategy

- **Investigate before assuming a design.** No schema anywhere in this codebase currently tracks "this alert was already sent" — a periodic task that queries `compute_budget_variance()`/`safety_proactive_warnings` on every tick and emails whenever the status is bad would re-send the same email every tick forever (unacceptable — the whole point of an "alert" is that it fires once per real state change, not once per scheduler interval). Decide and document as an ADR: a minimal dedup mechanism, most likely a small new table (`project_id`, `alert_type`, `last_sent_at`, maybe `last_status_value`) so a transition (e.g. `on_track` → `over_budget`) sends once, and the same bad status persisting across ticks does not re-send until either the status changes or a cooldown period elapses (a reasonable default like 24h — document the choice, this is exactly the kind of "not a derived figure, a convention" decision Sprint 14's `APPROACHING_BUDGET_THRESHOLD` already set precedent for documenting plainly rather than hiding).
- Decide who receives the email: likely every `owner`/`admin`/`project_manager`-role user in the alerting project's company (matching `STAFF_ONLY_ANALYTICS_ROLES`'s existing role set, ADR-056) — confirm this is the right set by checking how `Company`/`User` are actually related in `database/models/company.py`, not assumed.
- Decide the check interval (Celery Beat's own schedule, e.g. hourly) — favor a conservative, infrequent interval over a tight one; this is an alert system, not a real-time dashboard, and an infrequent check keeps both database load and worst-case email volume small.

### 2. `app/services/alert_service.py` — Alert Detection and Dedup Logic

- New service module, same shape as `cost_service.py`/`safety_trend_service.py`: given a project's already-computed `BudgetVariance`/safety-warning results (reusing Sprint 14/15's real functions, not reimplementing them) and the dedup table's last-sent record, decide whether a new alert should fire right now. Pure decision logic, testable without Celery or a real email send.
- Live-verify: a project transitioning from `on_track` to `over_budget` fires once; the same `over_budget` status on the next tick does not re-fire before the cooldown; a transition back to `on_track` (if that's a meaningful transition to notify on — decide during implementation) is handled explicitly, not accidentally.

### 3. Celery Beat Periodic Task

- New `app/tasks/alert_tasks.py` (or extend `app/tasks/`), registered in `celery_app.py`'s `beat_schedule`. Iterates every active project across every company (a cross-tenant sweep — this is legitimate background-process behavior, not a client-facing endpoint, so it does not go through `TenantScopedRepository`'s per-request scoping the way API code must), calls the Deliverable 2 decision logic per project, and sends real emails via the existing `EmailSender` for whatever should fire.
- A real Celery worker + Beat process must actually run this on schedule for the live-verification bar this project holds every sprint to — start a real `celery -A celery_app beat` process (a new component `docs/BACKEND_STARTUP.md` needs a short new section for) alongside the existing worker, force a bad-status project into the database, and confirm a real email appears in the `DevConsoleEmailSender` log within one tick interval.

### 4. Minimal Admin/Staff Visibility Into Alert History (If Time Allows)

- Lowest-priority deliverable, cut first if the first three consume the sprint's real effort: a small `GET /projects/{id}/alert-history` endpoint (or a section folded into the existing analytics endpoint) surfacing the dedup table's own record — "last budget alert sent: 2026-09-15, status was over_budget" — so a staff user isn't left guessing whether the system is actually working. Read-time-only projection over the same table Deliverable 1 designs, no new computation.

---

## Constraints

- **No paid APIs, no paid SaaS, no new infrastructure category.** Celery Beat ships with the already-pinned `celery` package; `EmailSender` already exists. This sprint is new *code* using entirely existing *infrastructure* — the same "no AI where deterministic logic suffices" discipline (ADR-005/007/048) applied to "no new scheduler when Celery Beat already fits."
- **Sprint 1-18 FROZEN.** New table (if Deliverable 1's dedup decision needs one) requires its own migration and ADR, per every prior sprint's schema-change precedent. Extend `app/services/`, `app/tasks/`, `celery_app.py`'s `beat_schedule`; do not modify `cost_service.py`'s or `safety_trend_service.py`'s existing computation functions unless a real, documented bug is found while integrating them.
- **A real Celery Beat process must actually run and be observed firing an alert** before this sprint is considered verified — the same live-verification bar as Sprint 9's real Celery worker/Redis/emailed-reset-link check. A dedup mechanism that only looks correct in a unit test, never observed actually preventing a real duplicate send, does not meet this project's standing discipline.
- **Continue the "explain, implement, test, verify" per-subsystem discipline.**

---

## Explicit Out of Scope for Sprint 19

- SMS, Slack, or any non-email notification channel — email via the existing `EmailSender` only, matching what this codebase already has working.
- Per-user notification preferences/opt-out UI — every `owner`/`admin`/`project_manager` in an alerting company's project receives the alert; a preferences system is a real, separate feature not named by this sprint's scope.
- Any Phase 5 product feature (Defect Detection, Bid Estimation) — both remain blocked exactly as Sprint 17 found them; not attempted here.
- Docker Compose — the disk-space constraint that deferred it in Sprint 18 may or may not still apply; if pursued, it should be its own sprint's clear focus, not bundled in alongside a notification system.
- Persisting `ServiceMetadata`/AI usage metrics — the other real candidate surfaced during Sprint 18's scoping, not this sprint's chosen focus. Remains open for a future sprint.
