"""
database/models/daily_log.py — DailyLog: the central table of the persistence layer.

This table is the database representation of ConstructionDailyLog v1.0.0.
Every other table in the schema either supports DailyLog (projects, workers,
audio_files) or is a child of DailyLog (log_work_items, log_delays, etc.).

Normalization strategy:
    Arrays of structured, independently queryable items → child tables.
    Deeply nested objects always fetched as a whole → JSON columns.

    Normalized (child tables in log_items.py):
        workforce.trades_on_site   → log_trades_on_site
        work_completed             → log_work_items
        work_in_progress           → log_work_in_progress
        materials.used_today       → log_materials_used
        materials.delivered_today  → log_materials_delivered
        materials.required_for_tomorrow → log_materials_required
        equipment                  → log_equipment
        safety.incidents           → log_safety_incidents
        safety.hazards_identified  → log_hazards
        delays                     → log_delays
        inspections                → log_inspections

    JSON blobs (always fetched complete, never queried by sub-field):
        weather                    → weather_json
        workforce late/absence/visitors → late_arrivals, absences, visitors
        materials.shortage_flags   → shortage_flags
        tomorrow_plan              → tomorrow_plan
        client_communication       → client_communication
        attachments                → attachments
        financials                 → financials

    Denormalized (stored twice intentionally):
        raw_transcript: also on SpeechTranscript.raw_text, but copied here
        so the daily log record is self-contained for API responses and
        AI generation without an extra JOIN. Documented as ADR-027.

Soft delete:
    DailyLog has soft delete. Approved daily logs are never hard-deleted.
    Deleted logs remain for audit purposes.

Review lifecycle:
    draft → under_review → approved | rejected
    Only approved logs feed downstream report generation and analytics.
"""
from __future__ import annotations

import uuid
from datetime import date as date_type, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.mixins import (
    AuditUserMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

if TYPE_CHECKING:
    from database.models.project import Project, Site
    from database.models.worker import Worker
    from database.models.audio import AudioFile, SpeechTranscript
    from database.models.generation import GenerationOutput
    from database.models.log_items import (
        LogTradeOnSite,
        LogWorkItem,
        LogWorkInProgress,
        LogMaterialUsed,
        LogMaterialDelivered,
        LogMaterialRequired,
        LogEquipment,
        LogSafetyIncident,
        LogHazard,
        LogDelay,
        LogInspection,
    )


class DailyLog(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, AuditUserMixin, Base):
    """The core daily site log record — one row per foreman voice recording per day.

    Maps directly to ConstructionDailyLog v1.0.0.
    Schema log_id → DailyLog.id (UUID v4).

    The Sprint 4 ExtractionResult.extracted_log dict is persisted into this table
    by the repository layer. The Sprint 5 GenerationResult is linked via the
    generation_outputs table (FK: daily_log_id).
    """

    __tablename__ = "daily_logs"

    # ── Foreign Keys ──────────────────────────────────────────────────────────
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
        doc="The project this log belongs to. RESTRICT — logs must be reassigned "
            "before a project can be deleted.",
    )
    site_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
        doc="The physical site this log covers. Nullable — multi-site project logs "
            "may be at the project level, not a specific site.",
    )
    audio_file_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("audio_files.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        doc="The voice recording this log was derived from. One-to-one: one audio "
            "file produces exactly one daily log. SET NULL preserves the log "
            "if the audio file is deleted.",
    )
    foreman_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("workers.id", ondelete="SET NULL"),
        nullable=True,
        doc="The foreman who recorded this log. Nullable — the foreman may not yet "
            "have a worker record in the system.",
    )

    # ── Log Metadata ──────────────────────────────────────────────────────────
    log_date: Mapped[date_type] = mapped_column(
        Date,
        nullable=False,
        doc="The calendar date this log covers. Not the creation timestamp. "
            "Format: YYYY-MM-DD. Unique per project per day (one log per project per day).",
    )
    log_source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="voice_recording",
        doc="How this log was created: voice_recording | manual_entry | "
            "mobile_app | web_app | api",
    )
    review_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="draft",
        doc="Approval lifecycle: draft | under_review | approved | rejected. "
            "Only approved logs feed downstream AI generation.",
    )
    review_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Notes added by reviewer when approving or rejecting. Required when "
            "status = rejected.",
    )
    reviewed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        doc="UUID of the User who reviewed this log. No FK — enforced at app layer.",
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        doc="UTC timestamp when the review decision was made.",
    )

    # ── Transcript (denormalized — ADR-027) ───────────────────────────────────
    raw_transcript: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="Verbatim transcript from Faster Whisper. Denormalized copy from "
            "speech_transcripts.raw_text. Kept here so daily log API responses "
            "are self-contained without joining audio_files + speech_transcripts.",
    )
    transcript_confidence: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4),
        nullable=True,
        doc="Average confidence score from Faster Whisper. 0.0–1.0. "
            "Denormalized from speech_transcripts.avg_confidence.",
    )

    # ── Construction Stage ────────────────────────────────────────────────────
    current_stage: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Primary active stage on this log date. Must be one of the 22 enum "
            "values from ConstructionDailyLog.current_stage.",
    )
    active_stages: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        doc="All stages with active work today. Multiple stages can run in parallel "
            "(e.g., electrical and plumbing rough-in). Array of stage code strings.",
    )
    stage_completion_percent: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        doc="Estimated completion of current_stage as of end of this log day. 0–100.",
    )
    overall_project_completion_percent: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        doc="Foreman's estimate of total project completion. 0–100. "
            "Used for customer progress updates.",
    )

    # ── Weather (JSON — ADR-028) ──────────────────────────────────────────────
    weather: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Full weather object from schema section 4. Stored as JSON because: "
            "weather is always fetched as a complete object (never query individual "
            "sub-fields), and 10 weather columns on a 40+ column table hurts "
            "readability. Sprint 13 Analytics can extract time-series via JSON "
            "operators in PostgreSQL.",
    )

    # ── Workforce Summary ─────────────────────────────────────────────────────
    total_workers_present: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Headcount of all workers on site today. Required field in schema.",
    )
    total_workers_scheduled: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    total_man_hours_worked: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        doc="Total labor hours across all workers today. Computed from trades_on_site "
            "or entered by foreman.",
    )
    late_arrivals: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        doc="Workers who arrived late. Array of {worker_identifier, trade, "
            "minutes_late, reason}. Kept as JSON — individual late arrivals are "
            "never queried independently at the log level.",
    )
    absences: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        doc="Workers who did not show up. Array of {worker_identifier, trade, "
            "reason, expected_return_date}.",
    )
    visitors: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        doc="Non-workers who visited the site. Array of {visitor_name, visitor_role, "
            "organization, visit_purpose, arrival_time, departure_time}.",
    )
    workforce_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # ── Safety Meeting ────────────────────────────────────────────────────────
    safety_meeting_conducted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Was a toolbox talk or safety meeting held today?",
    )
    safety_meeting_duration_minutes: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    safety_meeting_topics: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        doc="Array of topic strings discussed in the safety meeting.",
    )
    ppe_compliance_observed: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="full_compliance | minor_violations_corrected | violations_observed "
            "| not_monitored",
    )
    ppe_required_today: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        doc="Array of PPE code strings required for today's tasks. "
            "e.g. ['hard_hat', 'fall_protection_harness'].",
    )
    safety_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # ── Material Shortage Flags ───────────────────────────────────────────────
    shortage_flags: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        doc="Materials running low. Array of {material_name, severity, "
            "estimated_days_remaining, impact_on_schedule, action_required}. "
            "Feeds the Material Reminder AI service.",
    )

    # ── Tomorrow's Plan (JSON — complex nested object) ────────────────────────
    tomorrow_plan: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Foreman's plan for the next working day. Full nested object including "
            "planned_tasks, materials_to_order, equipment_needed, subcontractors_scheduled, "
            "inspections_scheduled, workers_expected, plan_notes. "
            "Stored as JSON — always consumed as a complete object by AI generators.",
    )

    # ── Client Communication (JSON) ───────────────────────────────────────────
    client_communication: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Any client contact today. Full object: client_contacted_today, "
            "contact_method, topics_discussed, client_concerns, change_orders, "
            "communication_notes. Always consumed as a complete object.",
    )

    # ── Attachments (JSON — future Sprint Defect Detection module) ────────────
    attachments: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        doc="Photos, videos, and documents. Array of attachment objects. "
            "Sprint 14 Defect Detection will normalize these into their own table; "
            "for Sprint 6 we capture the JSON to avoid losing data.",
    )

    # ── Financials (JSON — future Cost Intelligence module) ───────────────────
    financials: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        doc="Daily cost tracking. Object with daily_labor_cost_usd, "
            "daily_material_cost_usd, daily_equipment_cost_usd, etc. "
            "Sprint 14 Cost Intelligence module uses these values.",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    project: Mapped["Project"] = relationship("Project", back_populates="daily_logs")
    site: Mapped[Optional["Site"]] = relationship("Site", back_populates="daily_logs")
    audio_file: Mapped[Optional["AudioFile"]] = relationship(
        "AudioFile", back_populates="daily_log"
    )
    foreman: Mapped[Optional["Worker"]] = relationship(
        "Worker", foreign_keys=[foreman_id]
    )
    generation_outputs: Mapped[list["GenerationOutput"]] = relationship(
        "GenerationOutput",
        back_populates="daily_log",
        cascade="all, delete-orphan",
    )

    # Child tables — cascade delete when log is deleted
    trades_on_site: Mapped[list["LogTradeOnSite"]] = relationship(
        "LogTradeOnSite", back_populates="daily_log", cascade="all, delete-orphan"
    )
    work_items: Mapped[list["LogWorkItem"]] = relationship(
        "LogWorkItem", back_populates="daily_log", cascade="all, delete-orphan"
    )
    work_in_progress: Mapped[list["LogWorkInProgress"]] = relationship(
        "LogWorkInProgress", back_populates="daily_log", cascade="all, delete-orphan"
    )
    materials_used: Mapped[list["LogMaterialUsed"]] = relationship(
        "LogMaterialUsed", back_populates="daily_log", cascade="all, delete-orphan"
    )
    materials_delivered: Mapped[list["LogMaterialDelivered"]] = relationship(
        "LogMaterialDelivered", back_populates="daily_log", cascade="all, delete-orphan"
    )
    materials_required: Mapped[list["LogMaterialRequired"]] = relationship(
        "LogMaterialRequired", back_populates="daily_log", cascade="all, delete-orphan"
    )
    equipment: Mapped[list["LogEquipment"]] = relationship(
        "LogEquipment", back_populates="daily_log", cascade="all, delete-orphan"
    )
    safety_incidents: Mapped[list["LogSafetyIncident"]] = relationship(
        "LogSafetyIncident", back_populates="daily_log", cascade="all, delete-orphan"
    )
    hazards: Mapped[list["LogHazard"]] = relationship(
        "LogHazard", back_populates="daily_log", cascade="all, delete-orphan"
    )
    delays: Mapped[list["LogDelay"]] = relationship(
        "LogDelay", back_populates="daily_log", cascade="all, delete-orphan"
    )
    inspections: Mapped[list["LogInspection"]] = relationship(
        "LogInspection", back_populates="daily_log", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # One log per project per day (core business rule)
        UniqueConstraint("project_id", "log_date", name="uq_daily_logs_project_date"),
        Index("ix_daily_logs_project_id", "project_id"),
        Index("ix_daily_logs_log_date", "log_date"),
        Index("ix_daily_logs_review_status", "review_status"),
        Index("ix_daily_logs_current_stage", "current_stage"),
        # Compound: most common query pattern in Sprint 7 API
        Index("ix_daily_logs_project_date_status", "project_id", "log_date", "review_status"),
    )

    def __repr__(self) -> str:
        return (
            f"<DailyLog id={self.id} "
            f"project={self.project_id} "
            f"date={self.log_date} "
            f"status={self.review_status!r}>"
        )
