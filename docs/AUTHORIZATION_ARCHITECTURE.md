# Authorization Architecture — Sprint 8

**Package:** `app/core/permissions.py`, `app/api/dependencies.py`, `database/repositories/tenant.py`
**Status:** COMPLETE
**Prerequisites:** Sprints 1–7 (FROZEN), Sprint 8 Subsystems 2, 3, 4, 6
**Companion doc:** `docs/AUTHENTICATION_ARCHITECTURE.md` (who you are)

This document explains authorization: once a request is authenticated (who you are), what you are allowed to do (permissions/RBAC), whose data you may touch (multi-tenancy), and how every authorization decision is recorded (audit). Authentication answers *who*; authorization answers *what* and *whose*.

---

## 1. The Layered Model

```
Request
  │
  ▼
Authentication  (get_current_user)         → 401 if not a valid, active user
  │
  ▼
Permission check (require_permission)       → 403 if the role lacks the permission
  │
  ▼
Tenant scoping   (TenantScopedRepository)   → 404 if the resource is another company's
  │
  ▼
Business rule    (service layer)            → 409 if the operation conflicts with state
  │
  ▼
Success
```

Each layer answers a different question and returns a different status code — see §6 for the full status-code policy.

---

## 2. RBAC: Role → Permission Set → Endpoint

**The design goal** (explicit spec requirement): do not hardcode role checks at endpoints. Instead: `Role → Permission Set → Endpoint Access`.

### Why extend the existing roles, not replace them

The spec's illustrative role list (System Admin, Company Admin, Project Manager, Site Engineer, Foreman, Worker, Read Only) did **not** match the roles already frozen in the Sprint 6 `User.role` column (`owner`, `admin`, `project_manager`, `foreman`, `safety_officer`, `client`). This was flagged as a real discrepancy and resolved by explicit decision:

- **Preserve all 6 existing roles** — they are in the frozen Sprint 6 schema, already seeded, already covered by Sprint 7 tests. Renaming/replacing them would be a breaking change to a frozen artifact and would invalidate existing data.
- **Add exactly one new role:** `system_admin` — a cross-company superuser concept that has no equivalent in the existing set (every existing role is implicitly scoped to one company; `system_admin` is not). Not seeded by default; provisioned deliberately by whoever operates the backend.
- **Implement RBAC as a permission layer** over these roles, mapping each role to a permission set — so the spec's real goal (fine-grained, centrally-defined access control, no hardcoded per-endpoint role lists) is met without a breaking migration.

### The permission catalog

`app/core/permissions.py` defines a `Permission` enum (25 permissions, `"<resource>:<action>"` naming, e.g. `daily_log:approve`, `user:create`, `company:read_any`) and `ROLE_PERMISSIONS` mapping each role to a `frozenset[Permission]`.

**Why a Python enum/dict, not a database table:** every permission is known at code-review time — this is a fixed, versioned-in-git catalog, not data an admin edits at runtime. A DB-backed permission table would need its own CRUD API, migration, and seed data for zero benefit over a dict literal that is exhaustively unit-testable and shows up in a diff when changed. Same reasoning as Sprint 5's `PromptRegistry`/`ServiceRegistry` (ADR-022/023).

### Role → permission summary

| Permission group | system_admin | owner / admin | project_manager | safety_officer | foreman | client |
|---|---|---|---|---|---|---|
| Read daily logs | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Submit daily logs | ✅ | ✅ | ✅ | — | ✅ | — |
| Approve / reject logs | ✅ | ✅ | ✅ | — | — | — |
| Generate documents | ✅ | ✅ | ✅ | — | — | — |
| Upload audio | ✅ | ✅ | ✅ | — | ✅ | — |
| Read projects | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| User management (CRUD) | ✅ | ✅ | — | — | — | — |
| Assign roles / unlock | ✅ | ✅ | — | — | — | — |
| Read audit log | ✅ | ✅ | — | — | — | — |
| Cross-company (`*_any`) | ✅ | — | — | — | — | — |
| Manage own sessions | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

### Enforcement

`require_permission(Permission.X)` (`app/api/dependencies.py`) is the dependency every endpoint uses:

```python
@router.post("/daily-logs/{log_id}/approve")
def approve(..., user: CurrentUser = Depends(require_permission(Permission.DAILY_LOG_APPROVE))):
    ...
```

This replaced Sprint 7's hardcoded `require_role("owner", "project_manager")`. The difference: with `require_role`, every router that cares about approval independently had to know and agree on which roles that includes. With `require_permission`, which roles grant `DAILY_LOG_APPROVE` is decided in **exactly one place** (`ROLE_PERMISSIONS`) and every router asking about that permission automatically reflects it. `require_role()` remains for the rare genuinely-role-specific case, but permission checks are the default.

**Sprint 8 closed a real gap:** Sprint 7 had permission checks on only 2 endpoints (`approve`/`reject`); 7 others (`GET /daily-logs/{id}`, submit, generate, outputs, audio upload/status, project listing) had **no authorization check at all** — any authenticated user could reach them. All 9 are now permission-gated.

### Role assignment hierarchy

Role *assignment* (who can grant which role to whom) uses a separate authority ordering, `ROLE_RANK` (`app/core/permissions.py`), enforced by `UserService.assign_role()`:

- A user may only assign roles **at or below their own rank** — a company admin cannot create a `system_admin`, a project_manager cannot grant admin.
- A user can **never** change their own role, even holding `user:assign_role` — prevents a compromised owner session from silently self-escalating.
- Demoting/removing the **last owner-or-admin** in a company is blocked (409) — a company can never be left with no one able to administer it. The same guard applies to deactivation.

`ROLE_RANK`: `system_admin` (100) > `owner`/`admin` (80) > `project_manager` (60) > `foreman`/`safety_officer` (40) > `client` (20).

---

## 3. Multi-Tenancy: Repository-Layer Scoping

**The gap:** `CurrentUser.company_id` existed since Sprint 7 (decoded from the JWT) but **nothing checked it**. A `DailyLogRepository.get_by_id(log_id)` returned a resource belonging to any company. This was a real, exploitable data-isolation hole.

### Why enforce at the repository layer, not the router

Router-layer checks ("fetch, then compare `resource.company_id` to `user.company_id`, 404 on mismatch") require **every** router — present and future — to remember the comparison. Nothing structurally stops a new endpoint from calling `repo.get_by_id(id)` directly and shipping without it. Repository-layer enforcement removes that possibility: `TenantScopedRepository` (`database/repositories/tenant.py`) provides `*_scoped()` methods that build the company filter into the query itself. There is no unscoped read path for a company-owned table under normal use.

### `TenantContext`, not a raw `company_id`

Scoped methods take a `TenantContext` dataclass, always built via `TenantContext.from_current_user()` from the JWT-derived principal — **never from request input**. This directly serves the spec requirement "No endpoint should rely on client-supplied company IDs." A reviewer seeing `TenantContext` in a signature knows the value came from an authenticated principal; a bare `UUID` parameter conveys nothing.

### The scoped repositories

| Repository | company_id reached via |
|---|---|
| `ProjectRepository` | direct `Project.company_id` column |
| `DailyLogRepository` | join `DailyLog.project_id → Project.company_id` |
| `AudioRepository` | join via `project_id → Project.company_id` (nullable — unassigned audio is uploader-only) |
| `UserService` | direct `User.company_id` (one-line filter, no full subclass needed) |

`BaseRepository.get_by_id()`/`list()` were left untouched (they have no `TenantContext` and are used by Sprint 1–7 CLI/pipeline callers that already know their data is correctly scoped by construction). Subsystem 3 **added** scoped alternatives and migrated the HTTP routers to them — it did not retroactively break the base contract.

### System Admin bypass — explicit, audited, never automatic

`system_admin` is cross-company by design, so scoping needs an escape hatch. The design (explicit decision):

- **Separate, explicitly-named methods** (e.g. `get_by_id_cross_tenant()`), **never** a `company_id=None` sentinel on the normal scoped methods. A `None` that silently disables filtering is a landmine — a future refactor dropping an argument degrades into "no scoping" instead of failing loudly. An explicitly different method name cannot be reached by accident.
- Only reachable from a code path already gated by `Permission.COMPANY_READ_ANY` / `COMPANY_MANAGE_ANY`.
- **Every** cross-tenant call writes a mandatory `AuditLog` row (actor, target company, entity, action, request_id). This is the **one** audit event that is *not* fail-open (see §5) — a cross-tenant access that failed to audit must fail loudly, not silently succeed with no record.

---

## 4. Resource Enumeration Prevention: The Status-Code Policy

*(Also referenced in `docs/BACKEND_ARCHITECTURE.md`.)*

| Status | When | Example |
|---|---|---|
| **401 Unauthorized** | Authentication failed — no valid, active user | Missing/expired/invalid token |
| **403 Forbidden** | Authenticated, resource is in your tenant, but your role lacks the permission | A `client` calling `/daily-logs/{id}/submit` on their own company's log |
| **404 Not Found** | Resource doesn't exist **OR** belongs to another tenant | Company A requesting Company B's daily log by id |
| **409 Conflict** | Operation valid in general but conflicts with current state | Approving an already-approved log; demoting the last owner |
| **423 Locked** | Account locked by failed-login lockout | 6th login attempt after 5 failures |
| **429 Too Many Requests** | Rate limit exceeded | 11th login attempt in the window |

**Why 404 (not 403) for cross-tenant access:** a 403 would confirm "this id is a real resource, you're just not allowed to see it." A 404 makes a cross-tenant resource **indistinguishable from one that never existed** — no information leak. This matches the account-enumeration-avoidance posture already established at login/`get_current_user` (see `docs/AUTHENTICATION_ARCHITECTURE.md` §6). 403 is reserved for same-tenant-but-wrong-permission, where the resource is confirmed to exist and be accessible in principle.

Worked examples:
- `GET /daily-logs/{another-companys-id}` → **404** (indistinguishable from a nonexistent id)
- `POST /daily-logs/{own-companys-id}/submit` as a `client` → **403** (exists, in your tenant, wrong permission)
- `GET /daily-logs/{id}` with no `Authorization` header → **401**

---

## 5. Audit Logging of Authorization Decisions

Every authorization rejection and every sensitive authorization change writes a first-class `AuditLog` row.

### The `AuditLog` schema (Subsystem 6)

The Sprint 6 `AuditLog` table (`database/models/generation.py`) was extended with **first-class, queryable columns** (migration `004`):

| Column | Why first-class (not in `event_metadata` JSON) |
|---|---|
| `ip_address` | "every failed event from IP X in the last hour" → indexed column scan, not JSON-path filter |
| `user_agent` | consistent capture across every event |
| `request_id` | correlate one HTTP request's full audit footprint (one request can produce multiple events) |
| `success` | "all failed logins" is an indexed query |
| `target_user_id` | "every event done *to* this user" (vs *by* them) is one indexed query |

`event_metadata` (JSON) is **retained** for genuinely event-specific context with no cross-event meaning (`locked_until` for a lockout, `old_role`/`new_role` for a role change). The rule: if a future event type would *also* want the field, it's a column; if it's specific to one event's shape, it's `event_metadata`. **No field is duplicated** between a column and `event_metadata`.

**Why structured columns while keeping JSON** (explicit decision, see `docs/DECISIONS.md`): queryability (indexed scans for the common security queries), consistency (every call site passes the same typed parameter for the same concept, vs an unstructured dict where a future caller could use a different key name), and extensibility (JSON remains for the long tail).

### Authorization events

- `security.unauthorized_access` — every 401 rejection path in `get_current_user` (missing credentials, invalid JWT, missing claims, inactive/deleted user).
- `security.forbidden_access` — every 403 from `require_permission`, with the `required_permission` and the caller's `role`.
- `security.rate_limit_triggered` — rate-limit rejections.
- `user.role_changed` — role assignments (old/new role, actor, target).
- `system_admin.cross_tenant_access` — the mandatory, non-fail-open cross-tenant bypass event.

### Fail-open (with one exception)

`app/services/audit_helpers.py:safe_log_event()` wraps audit writes so a logging failure **never blocks business logic** — it catches any exception, logs it to the application logger, and returns None. It also **commits immediately** on success, so an audit row written just before a deliberately-raised `HTTPException` survives the request-scoped session's rollback (a real bug found in testing — see `docs/DECISIONS.md`).

The **one exception** is `system_admin.cross_tenant_access`, which uses the raw `log_event()` (must-succeed) — because "every cross-tenant access must generate an audit entry" is a stronger requirement than "logging must never block," and a cross-tenant access with no audit trail is worse than a failed one.

---

## 6. Backward Compatibility

All changes are additive. Existing roles and their behavior are preserved; `require_role()` still works; `BaseRepository`'s unscoped methods are unchanged (Sprint 1–7 callers unaffected); the `AuditLog` extension is a nullable-column migration compatible with every existing row. The only behavior changes are the closed authorization gaps (endpoints that previously had *no* check now enforce one) and the verified-bug fixes documented in `docs/DECISIONS.md`.
