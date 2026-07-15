"""
database/repositories/generation.py — GenerationOutput and AuditLog repositories.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models.generation import AuditLog, GenerationOutput
from database.repositories.base import BaseRepository


class GenerationRepository(BaseRepository[GenerationOutput]):
    """Repository for GenerationOutput (Sprint 5 AI service outputs)."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, GenerationOutput)

    def get_latest_for_log(
        self, daily_log_id: UUID, service_type: str
    ) -> Optional[GenerationOutput]:
        """Return the most recently created output for a log+service_type pair."""
        stmt = (
            select(GenerationOutput)
            .where(GenerationOutput.daily_log_id == daily_log_id)
            .where(GenerationOutput.service_type == service_type)
            .order_by(GenerationOutput.created_at.desc())
        )
        return self._session.execute(stmt).scalars().first()

    def list_for_log(self, daily_log_id: UUID) -> list[GenerationOutput]:
        """Return all generation outputs for a daily log (all service types)."""
        stmt = (
            select(GenerationOutput)
            .where(GenerationOutput.daily_log_id == daily_log_id)
            .order_by(GenerationOutput.service_type, GenerationOutput.created_at.desc())
        )
        return list(self._session.execute(stmt).scalars().all())

    def list_unsent(self, service_type: Optional[str] = None) -> list[GenerationOutput]:
        """Return valid, unsent outputs that are ready to deliver.

        Used by Sprint 7 background worker to process the delivery queue.
        """
        stmt = (
            select(GenerationOutput)
            .where(GenerationOutput.is_valid.is_(True))
            .where(GenerationOutput.is_sent.is_(False))
        )
        if service_type is not None:
            stmt = stmt.where(GenerationOutput.service_type == service_type)
        stmt = stmt.order_by(GenerationOutput.created_at)
        return list(self._session.execute(stmt).scalars().all())

    def mark_sent(self, output: GenerationOutput) -> GenerationOutput:
        """Mark an output as sent and record the send timestamp."""
        from datetime import datetime, timezone
        output.is_sent = True
        output.sent_at = datetime.now(timezone.utc)
        self._session.flush()
        return output

    def create_from_service_output(
        self,
        daily_log_id: Optional[UUID],
        service_output: object,
    ) -> GenerationOutput:
        """Persist a Sprint 5 ServiceOutput to the database.

        Accepts a Sprint 5 ServiceOutput Pydantic model. Uses duck typing
        (attribute access) to avoid importing from the generation/ package,
        preserving the clean boundary between generation/ (Sprint 5) and
        database/ (Sprint 6).
        """
        import uuid as uuid_mod

        output = GenerationOutput(
            daily_log_id=daily_log_id,
            service_type=str(getattr(service_output, "service_type", "")).lower().replace("servicetype.", "").replace(".", "_"),
            generation_id=uuid_mod.UUID(str(getattr(service_output.metadata, "generation_id", uuid_mod.uuid4()))),
            content=getattr(service_output, "content", ""),
            prompt_name=getattr(service_output.metadata, "prompt_name", None),
            prompt_version=getattr(service_output.metadata, "prompt_version", None),
            provider=getattr(service_output.metadata, "provider", None),
            model=getattr(service_output.metadata, "model", None),
            tokens_used=getattr(service_output.metadata, "total_tokens", None),
            response_time_ms=int(getattr(service_output.metadata, "response_time_seconds", 0) * 1000) or None,
            retry_count=getattr(service_output.metadata, "retry_count", 0),
            is_valid=getattr(service_output, "success", True),
            validation_errors=getattr(service_output, "errors", None) or None,
        )
        self._session.add(output)
        self._session.flush()
        return output


class AuditLogRepository(BaseRepository[AuditLog]):
    """Repository for AuditLog (immutable event records).

    IMPORTANT: Only create() is exposed. update() and soft_delete() from
    BaseRepository will still work at the ORM level but MUST NOT be called
    on AuditLog records. Business logic should treat AuditLog as append-only.
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session, AuditLog)

    def log_event(
        self,
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
    ) -> AuditLog:
        """Record an audit event. This is the only way to write to audit_logs.

        Sprint 8, Subsystem 6: target_user_id, ip_address, user_agent,
        request_id, and success are first-class parameters — pass them
        explicitly rather than folding them into `metadata`, so every
        caller uses the same field for the same concept (see
        database/models/generation.py AuditLog class docstring for the
        full rationale). `metadata` remains for genuinely event-specific
        extra context with no cross-event meaning.

        Never raises on a caller's behalf for logging-only failures —
        see docstring note on callers: business logic must not be
        blocked by a logging failure. This method itself can still raise
        if the session/DB is broken (a real infrastructure failure), but
        it does not add its own defensive try/except — callers that
        need "logging must never break the request" wrap the call site
        (see app/services/audit_helpers.py:safe_log_event() for the
        wrapper used by services that need that guarantee).

        Usage:
            audit_repo.log_event(
                "daily_log.approved",
                entity_type="daily_log",
                entity_id=log.id,
                actor_id=reviewer.id,
                company_id=project.company_id,
                old_values={"review_status": "under_review"},
                new_values={"review_status": "approved"},
            )
        """
        event = AuditLog(
            event_type=event_type,
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
            event_metadata=metadata,
        )
        self._session.add(event)
        self._session.flush()
        return event

    def list_by_request_id(self, request_id: str) -> list[AuditLog]:
        """Return every audit event produced by one HTTP request — a
        single login attempt can produce more than one event (e.g. a
        failed login followed by an account-lockout event), and this
        lets an operator see that whole story as one query."""
        stmt = (
            select(AuditLog)
            .where(AuditLog.request_id == request_id)
            .order_by(AuditLog.created_at)
        )
        return list(self._session.execute(stmt).scalars().all())

    def list_failures_by_ip(
        self, ip_address: str, *, since: Optional[datetime] = None, limit: int = 100,
    ) -> list[AuditLog]:
        """Return failed events from one IP address, optionally since a
        given time — the concrete "every failed login from IP X in the
        last hour" query this subsystem's structured columns exist to
        make cheap (an indexed column scan, not a JSON-path filter)."""
        stmt = (
            select(AuditLog)
            .where(AuditLog.ip_address == ip_address)
            .where(AuditLog.success.is_(False))
        )
        if since is not None:
            stmt = stmt.where(AuditLog.created_at >= since)
        stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
        return list(self._session.execute(stmt).scalars().all())

    def list_for_target_user(self, target_user_id: UUID, *, limit: int = 100) -> list[AuditLog]:
        """Return every event done TO a user (not BY them) — e.g. every
        time this user was deactivated, had their role changed, or was
        unlocked by someone else."""
        stmt = (
            select(AuditLog)
            .where(AuditLog.target_user_id == target_user_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return list(self._session.execute(stmt).scalars().all())

    def list_for_entity(
        self,
        entity_type: str,
        entity_id: UUID,
        *,
        limit: int = 50,
    ) -> list[AuditLog]:
        """Return the audit trail for a specific entity, newest first."""
        stmt = (
            select(AuditLog)
            .where(AuditLog.entity_type == entity_type)
            .where(AuditLog.entity_id == entity_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return list(self._session.execute(stmt).scalars().all())

    def list_by_company(
        self,
        company_id: UUID,
        *,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[AuditLog]:
        """Return recent audit events for a company."""
        stmt = (
            select(AuditLog)
            .where(AuditLog.company_id == company_id)
        )
        if event_type is not None:
            stmt = stmt.where(AuditLog.event_type == event_type)
        stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
        return list(self._session.execute(stmt).scalars().all())
