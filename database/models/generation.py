"""
database/models/generation.py — GenerationOutput and AuditLog tables.

GenerationOutput:
    Stores the 4 AI-generated outputs produced by Sprint 5's generation/ package.
    One GenerationOutput row per (daily_log, service_type) pair.
    The Sprint 5 GenerationResult contains all 4 service outputs; each becomes
    one row in this table, linked to the daily_log that sourced the input data.

    Why one row per output (not one row per GenerationResult):
        • Each output has its own validation status, send status, and content.
        • A failed daily_report must not invalidate a successful customer_update.
        • Sprint 7 API will expose /logs/{id}/generation/{service_type} endpoints.
        • Per-output tracking enables partial regeneration (re-run only safety_talk).

    Why store the full content as TEXT (not separate structured columns):
        • The outputs are Markdown/prose text. No structured sub-fields to query.
        • Sprint 9 frontend renders the text directly.
        • Storing as TEXT lets us retrieve the output with a single column read.

AuditLog:
    Immutable event log capturing every significant state transition in the system.
    WHO changed WHAT from WHAT to WHAT, and WHEN.

    Why AuditLog is immutable (no updated_at, no soft delete):
        • An audit log that can be updated is not an audit log.
        • GDPR right-to-erasure: the event "user X data was deleted" is itself
          audit-worthy and must survive the deletion.
        • Insurance and OSHA compliance: incident records must be permanent.

    This table must NEVER have UPDATE or DELETE statements issued against it.
    The repository enforces this by providing only a create() method.

    actor_id and company_id have NO FK constraints intentionally:
        • The actor may be a deleted user (their audit trail must remain).
        • company_id must survive even if the company is later deleted.
        • This mirrors the AuditUserMixin pattern (ADR-026).

    Sprint 8, Subsystem 6 (Security Audit Logging) additions — ip_address,
    user_agent, request_id, success, target_user_id — are first-class
    columns, not fields buried inside event_metadata:
        • Queryability: "every failed login from IP X in the last hour"
          or "every event tied to request_id Y" becomes an indexed
          column scan instead of a JSON-path filter across every row.
        • Consistency: every log_event() call site passes these through
          the same typed keyword arguments (see
          database/repositories/generation.py:AuditLogRepository), so a
          future caller cannot accidentally use a different key name
          for the same concept the way an unstructured metadata dict
          would allow.
        • event_metadata is retained, unchanged, for genuinely
          event-specific extra context that has no general cross-event
          meaning (e.g. "locked_until" only makes sense for a lockout
          event, "old_role"/"new_role" only for a role-change event) —
          the boundary is: if a future event type would ALSO want this
          field, it belongs as a column; if it's specific to one event
          type's shape, it belongs in event_metadata. No field is
          duplicated between a column and event_metadata.
    """
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from database.models.daily_log import DailyLog


class GenerationOutput(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single AI-generated output for a daily log.

    Maps to one ServiceOutput within Sprint 5's GenerationResult.
    Four rows per daily log (one per service_type), or fewer if only
    specific services were run.

    Lifecycle:
        created     — generation just completed, content stored
        sent        — output was delivered to the recipient (email sent, etc.)
        superseded  — a newer generation exists for this log + service_type
    """

    __tablename__ = "generation_outputs"

    daily_log_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("daily_logs.id", ondelete="SET NULL"),
        nullable=True,
        doc="The daily log this output was generated from. SET NULL so that "
            "deleting a draft log does not destroy the generated outputs "
            "a PM may have already reviewed.",
    )

    # ── Generation Identity ───────────────────────────────────────────────────
    service_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Which AI service produced this output: "
            "daily_report | customer_update | safety_talk | material_reminder",
    )
    generation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        doc="UUID4 correlation ID from Sprint 5 ServiceMetadata.generation_id. "
            "Links this DB row to logger lines, events, and metrics from the "
            "generation run. Indexed for cross-system tracing.",
    )

    # ── Generated Content ─────────────────────────────────────────────────────
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="The full generated text output (Markdown or plain text). "
            "e.g., the full daily report in Markdown format.",
    )

    # ── Prompt Metadata (for audit and regeneration) ──────────────────────────
    prompt_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="Name of the prompt template used. e.g., 'daily_report'",
    )
    prompt_version: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        doc="Frontmatter version from the .md prompt file. e.g., '1.0.0'",
    )

    # ── LLM Provider Metadata ─────────────────────────────────────────────────
    provider: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="LLM provider used. e.g., 'groq'",
    )
    model: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="Model name. e.g., 'llama-3.3-70b-versatile'",
    )
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="LLM response time in milliseconds. Used for SLA monitoring.",
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of retries before success. 0 = succeeded on first attempt.",
    )

    # ── Validation ────────────────────────────────────────────────────────────
    is_valid: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        doc="Result of Sprint 5 ContentValidator. False if output failed quality checks.",
    )
    validation_errors: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        doc="List of ContentValidator error strings if is_valid=False.",
    )

    # ── Delivery Status ───────────────────────────────────────────────────────
    is_sent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="True once this output was delivered to the recipient "
            "(email sent, Slack message sent, etc.). Sprint 7 sets this flag.",
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="UTC timestamp when this output was sent. Null if not yet sent.",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    daily_log: Mapped[Optional["DailyLog"]] = relationship(
        "DailyLog", back_populates="generation_outputs"
    )

    __table_args__ = (
        # One output per log per service type per generation run
        # (generation_id differentiates multiple runs for the same log+service)
        UniqueConstraint(
            "daily_log_id", "service_type", "generation_id",
            name="uq_generation_outputs_log_service_run",
        ),
        Index("ix_generation_outputs_daily_log_id", "daily_log_id"),
        Index("ix_generation_outputs_service_type", "service_type"),
        Index("ix_generation_outputs_generation_id", "generation_id"),
        Index("ix_generation_outputs_is_sent", "is_sent"),
    )

    def __repr__(self) -> str:
        return (
            f"<GenerationOutput service={self.service_type!r} "
            f"valid={self.is_valid} sent={self.is_sent}>"
        )


class AuditLog(UUIDPrimaryKeyMixin, Base):
    """Immutable event record for every significant state change.

    Written by the repository layer on every create/update/delete of a
    mutable entity. Never updated. Never deleted (except GDPR erasure, which
    writes a new "data_erased" event rather than removing the old events).

    This table has no TimestampMixin because:
        • updated_at is meaningless on an immutable table.
        • created_at is added explicitly here with server_default=func.now()
          so the DB sets the timestamp — not the application clock.

    actor_id / company_id have NO FK constraints by design (see module docstring).
    """

    __tablename__ = "audit_logs"

    # created_at is the only timestamp — set by DB server on INSERT
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        doc="UTC timestamp of this event. Set by the database server, not the "
            "application. This is the authoritative event time.",
    )

    # ── Event Classification ──────────────────────────────────────────────────
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Dot-namespaced event type. e.g., 'daily_log.created', "
            "'daily_log.approved', 'project.deleted', 'user.login_failed'",
    )
    entity_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="The type of entity affected. e.g., 'daily_log', 'project', 'worker'",
    )
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        doc="UUID of the affected record. No FK — the record may be deleted later "
            "but the audit trail must remain.",
    )

    # ── Actor (who did this) ──────────────────────────────────────────────────
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        doc="UUID of the User who triggered this event. No FK — enforced at app layer. "
            "Null for system-generated events (scheduled jobs, seed scripts).",
    )
    company_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        doc="Company scoping for multi-tenancy queries. No FK — the company may be "
            "deleted but the audit trail must survive.",
    )
    target_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        doc="Sprint 8: the User the event was DONE TO, when different from "
            "the actor — e.g. actor_id is the admin who deactivated someone, "
            "target_user_id is the user who got deactivated. For an event "
            "with no distinct target (e.g. a plain login), this is null; "
            "entity_id already covers 'what record changed' for non-user "
            "entities (daily_log, project, etc.) — target_user_id exists "
            "specifically so 'every event done TO this user' is one "
            "indexed query, not entity_type='user' AND entity_id=X mixed "
            "with actor_id=X cases that mean different things.",
    )

    # ── Request context (Sprint 8, Subsystem 6) ──────────────────────────────
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
        doc="Client IP at the time of this event. 45 chars fits IPv6.",
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="Raw User-Agent header at the time of this event.",
    )
    request_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        doc="The X-Request-ID (app/middleware/request_id.py) of the HTTP "
            "request that produced this event — correlates this row to "
            "the structured request log line and lets an operator trace "
            "one HTTP request's full audit footprint (it may produce more "
            "than one event, e.g. a failed login followed by a lockout).",
    )
    success: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        doc="Whether the action this event describes succeeded. Nullable "
            "(not defaulted to True) because some event types are purely "
            "informational and success/failure doesn't apply to them "
            "(e.g. 'user.profile_updated' — the fact that a row exists "
            "means it succeeded; a null here just means 'not applicable', "
            "distinct from an explicit False).",
    )

    # ── Change Data ───────────────────────────────────────────────────────────
    old_values: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Snapshot of the entity's relevant fields before the change. "
            "Only non-null on update and delete events.",
    )
    new_values: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Snapshot of the entity's relevant fields after the change. "
            "Null on delete events.",
    )
    event_metadata: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Extra, event-type-specific context that has no general "
            "cross-event meaning — e.g. 'locked_until' for a lockout "
            "event, 'old_role'/'new_role' for a role change. ip_address, "
            "user_agent, request_id, and success moved to first-class "
            "columns in Sprint 8 (see class docstring) — do not "
            "duplicate them here. Named event_metadata (not metadata) "
            "because metadata is reserved by SQLAlchemy's Declarative API.",
    )

    __table_args__ = (
        Index("ix_audit_logs_event_type", "event_type"),
        Index("ix_audit_logs_ip_address", "ip_address"),
        Index("ix_audit_logs_request_id", "request_id"),
        Index("ix_audit_logs_target_user_id", "target_user_id"),
        Index("ix_audit_logs_success", "success"),
        Index("ix_audit_logs_entity_type_id", "entity_type", "entity_id"),
        Index("ix_audit_logs_actor_id", "actor_id"),
        Index("ix_audit_logs_company_id", "company_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog event={self.event_type!r} "
            f"entity={self.entity_type!r}:{self.entity_id} "
            f"at={self.created_at}>"
        )
