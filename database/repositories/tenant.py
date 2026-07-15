"""
database/repositories/tenant.py — TenantContext and TenantScopedRepository.

Sprint 8, Subsystem 3 (Multi-Tenancy Scoping). This is the enforcement
mechanism behind the gap docs/ROADMAP.md names explicitly: "No endpoint
should rely on client-supplied company IDs... every repository/service
should automatically scope queries to the authenticated company." Prior
to this subsystem, CurrentUser.company_id existed (Sprint 7) but nothing
checked it — a repository's get_by_id() would happily return a resource
belonging to a different company than the caller's, because no query
anywhere filtered by company_id unless a caller happened to remember to
pass one to a *_by_company() convenience method.

Why repository-layer enforcement, not router-layer checks (explicit
architectural decision):
    A router-layer check ("fetch the resource, then compare
    resource.company_id to user.company_id, 404 if mismatched") requires
    every router, present and future, to remember to add that comparison.
    Nothing stops a new endpoint from calling repo.get_by_id(id) directly
    and shipping without the check — the unscoped code path still exists
    and is one missed line away from a real cross-tenant data leak.
    Repository-layer enforcement removes that possibility structurally:
    TenantScopedRepository's query methods take a TenantContext and build
    the company filter into the query itself. There is no unscoped read
    path for a company-owned table under normal use — see "System Admin
    bypass" below for the one explicit, audited exception.

Why a TenantContext dataclass instead of passing a raw company_id: UUID:
    A raw UUID at a call site (`repo.get_scoped(id, some_uuid)`) gives no
    signal about *why* that UUID is there or where it came from — it's
    interchangeable with any other UUID in the function, including one
    that was never validated against the actual authenticated user (e.g.
    a client-supplied company_id in a request body, which
    docs/ROADMAP.md explicitly calls out as a case to prevent: "No
    endpoint should rely on client-supplied company IDs"). TenantContext
    is built in exactly one place — see from_current_user() below — always
    from the JWT-derived CurrentUser, never from request input. A
    reviewer scanning a diff sees `TenantContext` in a function signature
    and knows immediately "this method is tenant-scoped, and the value
    can only have come from an authenticated principal," which a bare
    `UUID` parameter cannot convey.

Why company-owned repositories never expose an unscoped query path
(structural requirement, not just convention):
    Every read/write method on a TenantScopedRepository subclass that
    touches a company-owned row requires a TenantContext parameter. There
    is no `get_by_id(id)` overload without one. A caller that wants
    unscoped access must go through the explicitly separate, permission-
    gated System Admin bypass methods (see below) — never by omitting an
    argument or passing a sentinel value on the normal path.

System Admin bypass — design (explicit user requirements, do not deviate):
    - Kept as SEPARATE, explicitly-named methods (e.g. get_by_id_cross_tenant()),
      never a company_id=None on the normal scoped methods. A None default
      that silently disables filtering is a landmine: a future refactor
      that drops an argument, or a router bug that fails to pass a real
      TenantContext, degrades into "no scoping" instead of failing loudly.
      An explicitly different method name cannot be reached by accident.
    - Only reachable from code paths already gated by
      Permission.COMPANY_READ_ANY / COMPANY_MANAGE_ANY (see
      app/core/permissions.py) — enforced by require_permission() at the
      router layer before a bypass method is ever called.
    - Every bypass call MUST write an AuditLog row (actor, target company,
      entity, action, request_id, timestamp) via AuditLogRepository — see
      audit_cross_tenant_access() below, which every bypass method calls
      before returning. There is no cross-tenant read that does not also
      produce an audit trail.

Why 404, not 403, for cross-tenant access attempts (see
docs/AUTHORIZATION_ARCHITECTURE.md for the full writeup once written):
    Matches the account-enumeration-avoidance precedent already
    established in this codebase (POST /auth/login and get_current_user()
    both return an identical response regardless of which specific
    failure occurred, so an attacker cannot use response differences to
    learn anything). A 403 on a cross-tenant request would confirm "this
    ID is real, you're just not allowed to see it" — a 404 makes a
    cross-tenant resource indistinguishable from one that never existed.
    403 remains correct for same-tenant-but-wrong-permission (the
    resource is confirmed to exist and be accessible in principle, the
    caller's role just isn't allowed to act on it — see
    app/api/dependencies.py:require_permission()).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Optional, Type, TypeVar
from uuid import UUID

from sqlalchemy.orm import Session

from database.repositories.base import BaseRepository

T = TypeVar("T")


@dataclass(frozen=True)
class TenantContext:
    """The authenticated tenant scope for one request.

    Always constructed via from_current_user() — never built from
    request-supplied data. See module docstring.
    """

    company_id: UUID
    user_id: UUID

    @classmethod
    def from_current_user(cls, user: "object") -> "TenantContext":
        """Build a TenantContext from an app.api.dependencies.CurrentUser.

        Typed as `object` here (not CurrentUser) to avoid database/
        importing from app/ — see ADR-032 (docs/DECISIONS.md): database/
        has zero dependency on app/, and this repository module must
        stay importable from a CLI script or test that never imports
        FastAPI. Callers in app/ pass a real CurrentUser; duck typing on
        .company_id/.user_id is sufficient and keeps the dependency
        direction correct.
        """
        return cls(company_id=user.company_id, user_id=user.user_id)  # type: ignore[attr-defined]


class TenantScopedRepository(BaseRepository[T], Generic[T]):
    """Base class for repositories over company-owned tables.

    Subclasses must implement _company_id_filter() to describe how to
    constrain a SELECT to one company — either a direct column
    comparison (Project.company_id == ...) or a join up to Project/
    Company for tables that only reach company_id indirectly (DailyLog,
    AudioFile, Site, ProjectWorker). See each subclass for its specific
    join path.

    This class does NOT override BaseRepository's get_by_id()/list() —
    those remain available but are the caller's responsibility to avoid
    for company-owned tables. Subclasses instead ADD *_scoped() methods
    that are the intended, safe entry point. This is a deliberate
    trade-off: making get_by_id() itself tenant-aware would require every
    call site in Sprints 1-7 (CLI scripts, seed scripts, existing
    Sprint 6/7 code with no TenantContext available) to be rewritten
    or broken. Subsystem 3 adds scoped alternatives and migrates the
    app/api/v1/*.py routers (the only tenant-facing callers) to use them;
    it does not retroactively change BaseRepository's contract.
    """

    def __init__(self, session: Session, model: Type[T]) -> None:
        super().__init__(session, model)

    def _audit_cross_tenant_access(
        self,
        *,
        tenant_context_actor: "TenantContext",
        target_company_id: Optional[UUID],
        entity_type: str,
        entity_id: Optional[UUID],
        action: str,
        request_id: Optional[str],
    ) -> None:
        """Write the mandatory audit trail entry for a System Admin
        cross-tenant bypass call. Called by every *_cross_tenant() method
        in subclasses before returning — see module docstring "System
        Admin bypass."
        """
        from database.repositories.generation import AuditLogRepository

        # Deliberately the raw AuditLogRepository.log_event(), NOT the
        # fail-open safe_log_event() wrapper (app/services/audit_helpers.py)
        # — a cross-tenant bypass is exactly the one category of event
        # where "audit logging must never block business logic" is
        # overridden by an even stronger requirement: "every cross-tenant
        # access must generate an audit log entry," full stop. If this
        # write fails, the bypass itself should fail loudly (propagate),
        # not silently succeed with no record it ever happened.
        AuditLogRepository(self._session).log_event(
            "system_admin.cross_tenant_access",
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=tenant_context_actor.user_id,
            company_id=target_company_id,
            request_id=request_id,
            success=True,
            metadata={
                "action": action,
                "actor_home_company_id": str(tenant_context_actor.company_id),
            },
        )
