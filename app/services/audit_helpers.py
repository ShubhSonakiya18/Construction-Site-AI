"""
app/services/audit_helpers.py — Fail-open audit logging wrapper.

Sprint 8, Subsystem 6. Explicit requirement: "Never block business logic
if logging fails." database.repositories.generation.AuditLogRepository.log_event()
itself does not swallow exceptions — a broken DB connection during the
audit write should surface as a real error to whatever explicitly calls
log_event() directly and cares about the result (there currently are no
such callers; every existing call site treats it as fire-and-forget).

This module provides the fire-and-forget wrapper: safe_log_event() calls
log_event() and, if it raises for ANY reason, logs the failure to the
application logger and returns None instead of propagating — the request
that triggered the audit-worthy action still succeeds from the caller's
perspective. Audit logging is important, but it must never be the reason
a login, a role change, or a daily-log approval fails for the user.

Why safe_log_event() commits immediately on success (not just flush()):
    Several audit-worthy events are themselves the LAST thing that
    happens before the caller raises an HTTPException on purpose — e.g.
    app/api/dependencies.py:get_current_user() logs
    "security.unauthorized_access" immediately before raising 401, and
    require_permission() logs "security.forbidden_access" immediately
    before raising 403. The request-scoped session
    (database/session.py:get_session(), and its test mirror in
    tests/conftest_api.py) rolls back on ANY exception, including an
    intentionally-raised HTTPException — which would silently discard
    the just-flushed audit row along with everything else in that
    request's uncommitted work. This is the exact same class of bug
    documented in app/services/auth_service.py:_record_failed_login()
    (Subsystem 5) — found there first, and found again here by
    tests/test_audit_logging.py's security-event tests failing with
    "0 events recorded" despite the HTTP response being correct.
    Committing here means an audit row survives even when the
    surrounding request's other changes (if any) do not — acceptable,
    even correct, for an audit log: it is unrelated to and MORE durable
    than the transaction that triggered it.

Why a standalone function, not a method on AuditLogRepository:
    AuditLogRepository.log_event() is the low-level, honest primitive —
    "write this row, raise if you can't." Swallowing exceptions INSIDE
    the repository would hide real infrastructure problems from any
    future caller that legitimately needs to know a write failed (e.g. a
    future compliance-critical event that genuinely must not fail
    silently). Keeping the fail-open behavior in a separate wrapper
    function makes it opt-in per call site, not baked into the
    repository's contract.

Why NOT a decorator or context manager:
    A plain function call reads clearly at every call site
    (`safe_log_event(repo, "user.login", ...)` vs. wrapping the entire
    surrounding business logic in a decorator/context manager that would
    also need to catch exceptions from code that has nothing to do with
    auditing). This keeps the blast radius of "logging is now optional"
    scoped to exactly the one write it wraps.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from database.models.generation import AuditLog
from database.repositories.generation import AuditLogRepository

logger = logging.getLogger("app.audit")


def safe_log_event(
    audit_repo: AuditLogRepository,
    event_type: str,
    *,
    entity_type: Optional[str] = None,
    entity_id: Optional[UUID] = None,
    actor_id: Optional[UUID] = None,
    company_id: Optional[UUID] = None,
    target_user_id: Optional[UUID] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    request_id: Optional[str] = None,
    success: Optional[bool] = None,
    old_values: Optional[dict] = None,
    new_values: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> Optional[AuditLog]:
    """Write an audit event; never raises. Returns the created AuditLog on
    success, or None if the write itself failed (logged as an error, not
    propagated) — see module docstring.

    Same parameter shape as AuditLogRepository.log_event() — this is a
    transparent fail-open wrapper, not a different API to learn.
    """
    try:
        event = audit_repo.log_event(
            event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            company_id=company_id,
            target_user_id=target_user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            success=success,
            old_values=old_values,
            new_values=new_values,
            metadata=metadata,
        )
        audit_repo._session.commit()  # see module docstring — must survive a caller-raised exception
        return event
    except Exception:
        logger.exception(
            "audit.safe_log_event: failed to record event_type=%s actor_id=%s "
            "entity_type=%s entity_id=%s — business operation proceeds regardless",
            event_type, actor_id, entity_type, entity_id,
        )
        return None
