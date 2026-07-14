"""
app/core/permissions.py — The permission catalog and role -> permission-set mapping.

Sprint 8. This is the single source of truth for "what can each role do,"
replacing per-endpoint require_role("owner", "project_manager") calls
scattered across app/api/v1/*.py (Sprint 7's only two, in daily_logs.py)
with one reusable layer:

    Role  →  Permission Set  →  Endpoint Access

Why extend the existing 6 roles instead of replacing them (see
docs/AUTHORIZATION_ARCHITECTURE.md for the full writeup):
    database/models/company.py's User.role column is frozen Sprint 6
    schema, already seeded, already covered by Sprint 7 tests. The
    project's own constraints (docs/HANDOVER.md §2: "Never modify
    completed Sprint artifacts unless fixing a verified bug") rule out
    renaming or replacing those values — this isn't a bug, it's a scope
    difference between the spec's illustrative role list and this
    project's actual, already-deployed one. A permission LAYER on top of
    the existing roles gets the spec's real goal (fine-grained,
    centrally-defined access control, no hardcoded per-endpoint role
    checks) without a breaking migration.

Why permissions are Python string constants, not a database table:
    Every permission this sprint needs is known at code-review time — this
    is a fixed, versioned-in-git set, not data an admin edits at runtime.
    A DB-backed permission table would need its own CRUD API, its own
    migration, and its own seed data for zero benefit over a dict literal
    that's exhaustively unit-testable and shows up in a diff when changed.
    Same reasoning as ADR-022 (PromptRegistry) and ADR-023
    (ServiceRegistry) — a registry in code for a fixed catalog, not a table.

Naming convention: "<resource>:<action>", e.g. "daily_log:approve".
    Grouping by resource makes ROLE_PERMISSIONS below scannable ("what can
    a foreman do to daily_logs? to audio? to users?") and makes a future
    per-resource permission audit ("list everyone who can approve logs")
    a single filter, not a cross-reference through role names.
"""
from __future__ import annotations

from enum import Enum


class Permission(str, Enum):
    """Every permission this backend enforces. Adding a new permission
    means adding one line here and granting it to the relevant roles in
    ROLE_PERMISSIONS below — no router changes required until a router
    actually starts checking the new permission."""

    # ── Daily logs ────────────────────────────────────────────────────────
    DAILY_LOG_READ = "daily_log:read"
    DAILY_LOG_SUBMIT = "daily_log:submit"
    DAILY_LOG_APPROVE = "daily_log:approve"
    DAILY_LOG_REJECT = "daily_log:reject"
    DAILY_LOG_GENERATE = "daily_log:generate"

    # ── Audio / pipeline ─────────────────────────────────────────────────
    AUDIO_UPLOAD = "audio:upload"
    AUDIO_READ = "audio:read"

    # ── Projects ──────────────────────────────────────────────────────────
    PROJECT_READ = "project:read"
    PROJECT_MANAGE = "project:manage"

    # ── Users (Subsystem 4) ──────────────────────────────────────────────
    USER_READ = "user:read"
    USER_CREATE = "user:create"
    USER_UPDATE = "user:update"
    USER_DEACTIVATE = "user:deactivate"
    USER_DELETE = "user:delete"
    USER_RESTORE = "user:restore"
    USER_ASSIGN_ROLE = "user:assign_role"

    # ── Company (cross-tenant, system_admin only) ────────────────────────
    COMPANY_READ_ANY = "company:read_any"
    COMPANY_MANAGE_ANY = "company:manage_any"

    # ── Audit log (Subsystem 6) ──────────────────────────────────────────
    AUDIT_LOG_READ = "audit_log:read"

    # ── Sessions (self-service, every authenticated role) ────────────────
    SESSION_MANAGE_OWN = "session:manage_own"


# ── Role -> Permission set ───────────────────────────────────────────────────
#
# Existing 6 roles (frozen, database/models/company.py User.role) plus the
# one new role this sprint adds: system_admin — a cross-company superuser
# concept that has no equivalent in the existing set (every existing role
# is implicitly scoped to one company; system_admin is not). See
# docs/AUTHORIZATION_ARCHITECTURE.md for the full role-to-permission
# rationale, including why each grant was made.

_COMPANY_SCOPED_MANAGEMENT: frozenset[Permission] = frozenset({
    Permission.DAILY_LOG_READ,
    Permission.DAILY_LOG_SUBMIT,
    Permission.DAILY_LOG_APPROVE,
    Permission.DAILY_LOG_REJECT,
    Permission.DAILY_LOG_GENERATE,
    Permission.AUDIO_UPLOAD,
    Permission.AUDIO_READ,
    Permission.PROJECT_READ,
    Permission.PROJECT_MANAGE,
    Permission.USER_READ,
    Permission.USER_CREATE,
    Permission.USER_UPDATE,
    Permission.USER_DEACTIVATE,
    Permission.USER_DELETE,
    Permission.USER_RESTORE,
    Permission.USER_ASSIGN_ROLE,
    Permission.AUDIT_LOG_READ,
    Permission.SESSION_MANAGE_OWN,
})

ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    # New in Sprint 8: cross-company superuser. Not seeded by default (see
    # database/seed/sample_data.py) — provisioned deliberately by whoever
    # operates this backend, not by any automatic bootstrap.
    "system_admin": frozenset(Permission),  # every permission, all companies

    # Existing roles — Sprint 6/7 unchanged values, permission sets
    # assigned fresh in Sprint 8.
    "owner": _COMPANY_SCOPED_MANAGEMENT,
    "admin": _COMPANY_SCOPED_MANAGEMENT,
    "project_manager": frozenset({
        Permission.DAILY_LOG_READ,
        Permission.DAILY_LOG_SUBMIT,
        Permission.DAILY_LOG_APPROVE,
        Permission.DAILY_LOG_REJECT,
        Permission.DAILY_LOG_GENERATE,
        Permission.AUDIO_UPLOAD,
        Permission.AUDIO_READ,
        Permission.PROJECT_READ,
        Permission.PROJECT_MANAGE,
        Permission.USER_READ,
        Permission.SESSION_MANAGE_OWN,
    }),
    "safety_officer": frozenset({
        Permission.DAILY_LOG_READ,
        Permission.AUDIO_READ,
        Permission.PROJECT_READ,
        Permission.USER_READ,
        Permission.SESSION_MANAGE_OWN,
    }),
    "foreman": frozenset({
        Permission.DAILY_LOG_READ,
        Permission.DAILY_LOG_SUBMIT,
        Permission.AUDIO_UPLOAD,
        Permission.AUDIO_READ,
        Permission.PROJECT_READ,
        Permission.SESSION_MANAGE_OWN,
    }),
    "client": frozenset({
        Permission.DAILY_LOG_READ,
        Permission.PROJECT_READ,
        Permission.SESSION_MANAGE_OWN,
    }),
}


def permissions_for_role(role: str) -> frozenset[Permission]:
    """Return the permission set for a role name. An unrecognized role
    (should not happen — User.role is application-validated, but this
    guards against data drift) gets zero permissions rather than raising,
    matching this codebase's fail-closed posture for authorization."""
    return ROLE_PERMISSIONS.get(role, frozenset())


def role_has_permission(role: str, permission: Permission) -> bool:
    return permission in permissions_for_role(role)
