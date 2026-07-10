"""Initial schema — all 26 tables

Revision ID: 001
Revises: (none — initial migration)
Create Date: 2026-07-10

Creates all 26 tables for Sprint 6 persistence layer:

Reference tables (4):
    trades, construction_stages, material_categories, ppe_types

Company/Auth tables (2):
    companies, users

Worker table (1):
    workers

Project tables (3):
    projects, sites, project_workers

Audio pipeline tables (2):
    audio_files, speech_transcripts

Core daily log table (1):
    daily_logs

Log child tables (11):
    log_trades_on_site, log_work_items, log_work_in_progress,
    log_materials_used, log_materials_delivered, log_materials_required,
    log_equipment, log_safety_incidents, log_hazards, log_delays, log_inspections

Generation tables (2):
    generation_outputs, audit_logs

PostgreSQL-specific choices in this migration (not in ORM models):
    - UUID columns use native PostgreSQL UUID type (not CHAR(32))
    - JSON columns use JSONB for indexability and compression
    - TIMESTAMPTZ used instead of TIMESTAMP for timezone awareness
    - gen_random_uuid() used as server-side default for UUID PKs
      as a fallback (Python-side default is uuid.uuid4 — whichever runs first wins)

Upgrade:   Creates all tables in dependency order.
Downgrade: Drops all tables in reverse order (children before parents).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Reference tables ──────────────────────────────────────────────────────
    op.create_table(
        "trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("is_licensed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("typical_crew_size", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_trades_code", "trades", ["code"])

    op.create_table(
        "construction_stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("sequence_order", sa.Integer, nullable=False),
        sa.Column("typical_duration_days", sa.Integer, nullable=False, server_default="5"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_construction_stages_code", "construction_stages", ["code"])
    op.create_index("ix_construction_stages_sequence", "construction_stages", ["sequence_order"])

    op.create_table(
        "material_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_material_categories_code", "material_categories", ["code"])

    op.create_table(
        "ppe_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("osha_reference", sa.String(100), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_ppe_types_code", "ppe_types", ["code"])

    # ── Company and users ─────────────────────────────────────────────────────
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("contact_email", sa.String(254), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(50), nullable=True),
        sa.Column("zip_code", sa.String(20), nullable=True),
        sa.Column("country", sa.String(100), nullable=False, server_default="USA"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("subscription_tier", sa.String(30), nullable=False, server_default="trial"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_companies_slug", "companies", ["slug"])
    op.create_index("ix_companies_is_active", "companies", ["is_active"])

    op.create_table(
        "workers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trade_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="laborer"),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("subcontractor_company", sa.String(200), nullable=True),
        sa.Column("license_number", sa.String(100), nullable=True),
        sa.Column("license_state", sa.String(10), nullable=True),
        sa.Column("emergency_contact_name", sa.String(200), nullable=True),
        sa.Column("emergency_contact_phone", sa.String(30), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT", name="fk_workers_company_id_companies"),
        sa.ForeignKeyConstraint(["trade_id"], ["trades.id"], ondelete="SET NULL", name="fk_workers_trade_id_trades"),
    )
    op.create_index("ix_workers_company_id", "workers", ["company_id"])
    op.create_index("ix_workers_trade_id", "workers", ["trade_id"])
    op.create_index("ix_workers_is_active", "workers", ["is_active"])

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(30), nullable=False, server_default="foreman"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT", name="fk_users_company_id_companies"),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], ondelete="SET NULL", name="fk_users_worker_id_workers"),
    )
    op.create_index("ix_users_company_id", "users", ["company_id"])
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_role", "users", ["role"])

    # ── Projects ──────────────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("project_type", sa.String(50), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="planning"),
        sa.Column("client_name", sa.String(200), nullable=True),
        sa.Column("client_contact_email", sa.String(254), nullable=True),
        sa.Column("client_contact_phone", sa.String(30), nullable=True),
        sa.Column("contractor_company", sa.String(200), nullable=True),
        sa.Column("project_size_sqft", sa.Numeric(12, 2), nullable=True),
        sa.Column("project_start_date", sa.Date, nullable=True),
        sa.Column("planned_completion_date", sa.Date, nullable=True),
        sa.Column("actual_completion_date", sa.Date, nullable=True),
        sa.Column("contract_value_usd", sa.Numeric(14, 2), nullable=True),
        sa.Column("permit_number", sa.String(100), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT", name="fk_projects_company_id_companies"),
    )
    op.create_index("ix_projects_company_id", "projects", ["company_id"])
    op.create_index("ix_projects_status", "projects", ["status"])
    op.create_index("ix_projects_company_status", "projects", ["company_id", "status"])

    op.create_table(
        "sites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(50), nullable=True),
        sa.Column("zip_code", sa.String(20), nullable=True),
        sa.Column("country", sa.String(100), nullable=False, server_default="USA"),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_sites_project_id_projects"),
    )
    op.create_index("ix_sites_project_id", "sites", ["project_id"])

    op.create_table(
        "project_workers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_on_project", sa.String(50), nullable=False, server_default="worker"),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_project_workers_project_id_projects"),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], ondelete="CASCADE", name="fk_project_workers_worker_id_workers"),
        sa.UniqueConstraint("project_id", "worker_id", name="uq_project_workers"),
    )
    op.create_index("ix_project_workers_project_id", "project_workers", ["project_id"])
    op.create_index("ix_project_workers_worker_id", "project_workers", ["worker_id"])

    # ── Audio pipeline ─────────────────────────────────────────────────────────
    op.create_table(
        "audio_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("stored_filename", sa.String(500), nullable=True),
        sa.Column("file_path", sa.String(1000), nullable=True),
        sa.Column("file_size_bytes", sa.Numeric(20, 0), nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("format", sa.String(10), nullable=True),
        sa.Column("duration_seconds", sa.Numeric(10, 3), nullable=True),
        sa.Column("sample_rate", sa.Integer, nullable=True),
        sa.Column("channels", sa.Integer, nullable=True),
        sa.Column("bit_depth", sa.Integer, nullable=True),
        sa.Column("is_valid", sa.Boolean, nullable=True),
        sa.Column("validation_errors", postgresql.JSONB, nullable=True),
        sa.Column("validation_warnings", postgresql.JSONB, nullable=True),
        sa.Column("processing_status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL", name="fk_audio_files_project_id_projects"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL", name="fk_audio_files_uploaded_by_id_users"),
    )
    op.create_index("ix_audio_files_project_id", "audio_files", ["project_id"])
    op.create_index("ix_audio_files_processing_status", "audio_files", ["processing_status"])

    op.create_table(
        "speech_transcripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("audio_file_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("language_code", sa.String(10), nullable=False, server_default="en"),
        sa.Column("language_probability", sa.Numeric(5, 4), nullable=True),
        sa.Column("duration_seconds", sa.Numeric(10, 3), nullable=True),
        sa.Column("avg_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("model_name", sa.String(100), nullable=True),
        sa.Column("model_size", sa.String(20), nullable=True),
        sa.Column("device_used", sa.String(20), nullable=True),
        sa.Column("compute_type", sa.String(20), nullable=True),
        sa.Column("processing_time_seconds", sa.Numeric(10, 3), nullable=True),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("total_segments", sa.Integer, nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("segments", postgresql.JSONB, nullable=True),
        sa.Column("stages_completed", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["audio_file_id"], ["audio_files.id"], ondelete="CASCADE", name="fk_speech_transcripts_audio_file_id_audio_files"),
    )
    op.create_index("ix_speech_transcripts_audio_file_id", "speech_transcripts", ["audio_file_id"])

    # ── Daily logs ────────────────────────────────────────────────────────────
    op.create_table(
        "daily_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("audio_file_id", postgresql.UUID(as_uuid=True), nullable=True, unique=True),
        sa.Column("foreman_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("log_date", sa.Date, nullable=False),
        sa.Column("log_source", sa.String(30), nullable=False, server_default="voice_recording"),
        sa.Column("review_status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("review_notes", sa.Text, nullable=True),
        sa.Column("reviewed_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("raw_transcript", sa.Text, nullable=True),
        sa.Column("transcript_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("current_stage", sa.String(50), nullable=False),
        sa.Column("active_stages", postgresql.JSONB, nullable=True),
        sa.Column("stage_completion_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("overall_project_completion_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("weather", postgresql.JSONB, nullable=True),
        sa.Column("total_workers_present", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_workers_scheduled", sa.Integer, nullable=True),
        sa.Column("total_man_hours_worked", sa.Numeric(10, 2), nullable=True),
        sa.Column("late_arrivals", postgresql.JSONB, nullable=True),
        sa.Column("absences", postgresql.JSONB, nullable=True),
        sa.Column("visitors", postgresql.JSONB, nullable=True),
        sa.Column("workforce_notes", sa.Text, nullable=True),
        sa.Column("safety_meeting_conducted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("safety_meeting_duration_minutes", sa.Integer, nullable=True),
        sa.Column("safety_meeting_topics", postgresql.JSONB, nullable=True),
        sa.Column("ppe_compliance_observed", sa.String(50), nullable=True),
        sa.Column("ppe_required_today", postgresql.JSONB, nullable=True),
        sa.Column("safety_notes", sa.Text, nullable=True),
        sa.Column("shortage_flags", postgresql.JSONB, nullable=True),
        sa.Column("tomorrow_plan", postgresql.JSONB, nullable=True),
        sa.Column("client_communication", postgresql.JSONB, nullable=True),
        sa.Column("attachments", postgresql.JSONB, nullable=True),
        sa.Column("financials", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT", name="fk_daily_logs_project_id_projects"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="SET NULL", name="fk_daily_logs_site_id_sites"),
        sa.ForeignKeyConstraint(["audio_file_id"], ["audio_files.id"], ondelete="SET NULL", name="fk_daily_logs_audio_file_id_audio_files"),
        sa.ForeignKeyConstraint(["foreman_id"], ["workers.id"], ondelete="SET NULL", name="fk_daily_logs_foreman_id_workers"),
        sa.UniqueConstraint("project_id", "log_date", name="uq_daily_logs_project_date"),
    )
    op.create_index("ix_daily_logs_project_id", "daily_logs", ["project_id"])
    op.create_index("ix_daily_logs_log_date", "daily_logs", ["log_date"])
    op.create_index("ix_daily_logs_review_status", "daily_logs", ["review_status"])
    op.create_index("ix_daily_logs_current_stage", "daily_logs", ["current_stage"])
    op.create_index("ix_daily_logs_project_date_status", "daily_logs", ["project_id", "log_date", "review_status"])

    # ── Log child tables (CASCADE from daily_logs) ────────────────────────────
    _child_tables = [
        ("log_trades_on_site", [
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("daily_log_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("trade", sa.String(50), nullable=False),
            sa.Column("workers_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("foreman_name", sa.String(200), nullable=True),
            sa.Column("subcontractor_company", sa.String(200), nullable=True),
            sa.Column("hours_worked", sa.Numeric(6, 2), nullable=True),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["daily_log_id"], ["daily_logs.id"], ondelete="CASCADE", name="fk_log_trades_on_site_daily_log_id_daily_logs"),
        ], [("ix_log_trades_daily_log_id", ["daily_log_id"]), ("ix_log_trades_trade", ["trade"])]),
        ("log_work_items", [
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("daily_log_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("task_description", sa.Text, nullable=False),
            sa.Column("trade", sa.String(50), nullable=False),
            sa.Column("location_on_site", sa.String(200), nullable=True),
            sa.Column("quantity_completed", sa.Numeric(12, 3), nullable=True),
            sa.Column("unit_of_measure", sa.String(50), nullable=True),
            sa.Column("task_completion_percent", sa.Numeric(5, 2), nullable=True),
            sa.Column("linked_schedule_task_id", sa.String(100), nullable=True),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["daily_log_id"], ["daily_logs.id"], ondelete="CASCADE", name="fk_log_work_items_daily_log_id_daily_logs"),
        ], [("ix_log_work_items_daily_log_id", ["daily_log_id"]), ("ix_log_work_items_trade", ["trade"])]),
        ("log_work_in_progress", [
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("daily_log_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("task_description", sa.Text, nullable=False),
            sa.Column("trade", sa.String(50), nullable=True),
            sa.Column("location_on_site", sa.String(200), nullable=True),
            sa.Column("current_completion_percent", sa.Numeric(5, 2), nullable=True),
            sa.Column("expected_completion_date", sa.Date, nullable=True),
            sa.Column("blocking_issues", sa.Text, nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["daily_log_id"], ["daily_logs.id"], ondelete="CASCADE", name="fk_log_work_in_progress_daily_log_id_daily_logs"),
        ], [("ix_log_wip_daily_log_id", ["daily_log_id"])]),
        ("log_materials_used", [
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("daily_log_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("material_name", sa.String(200), nullable=False),
            sa.Column("category", sa.String(50), nullable=True),
            sa.Column("quantity_used", sa.Numeric(12, 3), nullable=False),
            sa.Column("unit", sa.String(50), nullable=False),
            sa.Column("waste_quantity", sa.Numeric(12, 3), nullable=True),
            sa.Column("unit_cost_usd", sa.Numeric(12, 4), nullable=True),
            sa.Column("supplier", sa.String(200), nullable=True),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["daily_log_id"], ["daily_logs.id"], ondelete="CASCADE", name="fk_log_materials_used_daily_log_id_daily_logs"),
        ], [("ix_log_materials_used_daily_log_id", ["daily_log_id"]), ("ix_log_materials_used_category", ["category"])]),
        ("log_materials_delivered", [
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("daily_log_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("material_name", sa.String(200), nullable=False),
            sa.Column("quantity_delivered", sa.Numeric(12, 3), nullable=False),
            sa.Column("unit", sa.String(50), nullable=False),
            sa.Column("supplier", sa.String(200), nullable=True),
            sa.Column("delivery_condition", sa.String(30), nullable=True),
            sa.Column("purchase_order_number", sa.String(100), nullable=True),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["daily_log_id"], ["daily_logs.id"], ondelete="CASCADE", name="fk_log_materials_delivered_daily_log_id_daily_logs"),
        ], [("ix_log_materials_delivered_daily_log_id", ["daily_log_id"])]),
        ("log_materials_required", [
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("daily_log_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("material_name", sa.String(200), nullable=False),
            sa.Column("quantity_needed", sa.Numeric(12, 3), nullable=False),
            sa.Column("unit", sa.String(50), nullable=False),
            sa.Column("urgency", sa.String(20), nullable=False, server_default="medium"),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["daily_log_id"], ["daily_logs.id"], ondelete="CASCADE", name="fk_log_materials_required_daily_log_id_daily_logs"),
        ], [("ix_log_materials_required_daily_log_id", ["daily_log_id"]), ("ix_log_materials_required_urgency", ["urgency"])]),
        ("log_equipment", [
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("daily_log_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("equipment_name", sa.String(200), nullable=False),
            sa.Column("equipment_type", sa.String(50), nullable=True),
            sa.Column("is_rented", sa.Boolean, nullable=True),
            sa.Column("hours_used", sa.Numeric(6, 2), nullable=True),
            sa.Column("operator", sa.String(200), nullable=True),
            sa.Column("equipment_condition", sa.String(30), nullable=True),
            sa.Column("maintenance_issues", sa.Text, nullable=True),
            sa.Column("fuel_consumed_liters", sa.Numeric(8, 2), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["daily_log_id"], ["daily_logs.id"], ondelete="CASCADE", name="fk_log_equipment_daily_log_id_daily_logs"),
        ], [("ix_log_equipment_daily_log_id", ["daily_log_id"]), ("ix_log_equipment_type", ["equipment_type"])]),
        ("log_safety_incidents", [
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("daily_log_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("incident_type", sa.String(50), nullable=False),
            sa.Column("description", sa.Text, nullable=False),
            sa.Column("worker_involved", sa.String(200), nullable=True),
            sa.Column("time_of_incident", sa.String(50), nullable=True),
            sa.Column("body_part_affected", sa.String(200), nullable=True),
            sa.Column("osha_recordable", sa.Boolean, nullable=True),
            sa.Column("medical_treatment_required", sa.Boolean, nullable=True),
            sa.Column("incident_reported_to", sa.String(200), nullable=True),
            sa.Column("corrective_actions", sa.Text, nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["daily_log_id"], ["daily_logs.id"], ondelete="CASCADE", name="fk_log_safety_incidents_daily_log_id_daily_logs"),
        ], [("ix_log_safety_incidents_daily_log_id", ["daily_log_id"]), ("ix_log_safety_incidents_type", ["incident_type"]), ("ix_log_safety_incidents_osha", ["osha_recordable"])]),
        ("log_hazards", [
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("daily_log_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("hazard_type", sa.String(50), nullable=False),
            sa.Column("location", sa.String(200), nullable=True),
            sa.Column("description", sa.Text, nullable=False),
            sa.Column("severity", sa.String(20), nullable=False),
            sa.Column("corrective_action", sa.Text, nullable=True),
            sa.Column("corrective_action_completed", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["daily_log_id"], ["daily_logs.id"], ondelete="CASCADE", name="fk_log_hazards_daily_log_id_daily_logs"),
        ], [("ix_log_hazards_daily_log_id", ["daily_log_id"]), ("ix_log_hazards_severity", ["severity"]), ("ix_log_hazards_type", ["hazard_type"])]),
        ("log_delays", [
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("daily_log_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("delay_type", sa.String(50), nullable=False),
            sa.Column("description", sa.Text, nullable=False),
            sa.Column("hours_lost", sa.Numeric(6, 2), nullable=True),
            sa.Column("workers_affected", sa.Integer, nullable=True),
            sa.Column("tasks_affected", postgresql.JSONB, nullable=True),
            sa.Column("schedule_impact", sa.String(50), nullable=True),
            sa.Column("days_lost_to_schedule", sa.Numeric(6, 2), nullable=True),
            sa.Column("resolution_action", sa.Text, nullable=True),
            sa.Column("delay_resolved", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("responsible_party", sa.String(200), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["daily_log_id"], ["daily_logs.id"], ondelete="CASCADE", name="fk_log_delays_daily_log_id_daily_logs"),
        ], [("ix_log_delays_daily_log_id", ["daily_log_id"]), ("ix_log_delays_type", ["delay_type"]), ("ix_log_delays_schedule_impact", ["schedule_impact"])]),
        ("log_inspections", [
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("daily_log_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("inspection_type", sa.String(50), nullable=False),
            sa.Column("inspector_name", sa.String(200), nullable=True),
            sa.Column("inspection_authority", sa.String(200), nullable=True),
            sa.Column("inspection_time", sa.String(50), nullable=True),
            sa.Column("result", sa.String(30), nullable=False),
            sa.Column("corrections_required", postgresql.JSONB, nullable=True),
            sa.Column("next_inspection_date", sa.Date, nullable=True),
            sa.Column("inspection_notes", sa.Text, nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["daily_log_id"], ["daily_logs.id"], ondelete="CASCADE", name="fk_log_inspections_daily_log_id_daily_logs"),
        ], [("ix_log_inspections_daily_log_id", ["daily_log_id"]), ("ix_log_inspections_type", ["inspection_type"]), ("ix_log_inspections_result", ["result"])]),
    ]

    for table_name, columns, indexes in _child_tables:
        op.create_table(table_name, *columns)
        for idx_name, idx_cols in indexes:
            op.create_index(idx_name, table_name, idx_cols)

    # ── Generation outputs ─────────────────────────────────────────────────────
    op.create_table(
        "generation_outputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("daily_log_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("service_type", sa.String(50), nullable=False),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("prompt_name", sa.String(100), nullable=True),
        sa.Column("prompt_version", sa.String(20), nullable=True),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("tokens_used", sa.Integer, nullable=True),
        sa.Column("response_time_ms", sa.Integer, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_valid", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("validation_errors", postgresql.JSONB, nullable=True),
        sa.Column("is_sent", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["daily_log_id"], ["daily_logs.id"], ondelete="SET NULL", name="fk_generation_outputs_daily_log_id_daily_logs"),
        sa.UniqueConstraint("daily_log_id", "service_type", "generation_id", name="uq_generation_outputs_log_service_run"),
    )
    op.create_index("ix_generation_outputs_daily_log_id", "generation_outputs", ["daily_log_id"])
    op.create_index("ix_generation_outputs_service_type", "generation_outputs", ["service_type"])
    op.create_index("ix_generation_outputs_generation_id", "generation_outputs", ["generation_id"])
    op.create_index("ix_generation_outputs_is_sent", "generation_outputs", ["is_sent"])

    # ── Audit log (immutable) ─────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("old_values", postgresql.JSONB, nullable=True),
        sa.Column("new_values", postgresql.JSONB, nullable=True),
        sa.Column("event_metadata", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"])
    op.create_index("ix_audit_logs_entity_type_id", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_company_id", "audit_logs", ["company_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    """Drop all tables in reverse dependency order (children before parents)."""
    # Audit / generation
    op.drop_table("audit_logs")
    op.drop_table("generation_outputs")

    # Log children
    for table in [
        "log_inspections", "log_delays", "log_hazards",
        "log_safety_incidents", "log_equipment",
        "log_materials_required", "log_materials_delivered", "log_materials_used",
        "log_work_in_progress", "log_work_items", "log_trades_on_site",
    ]:
        op.drop_table(table)

    # Core daily log
    op.drop_table("daily_logs")

    # Audio pipeline
    op.drop_table("speech_transcripts")
    op.drop_table("audio_files")

    # Project hierarchy
    op.drop_table("project_workers")
    op.drop_table("sites")
    op.drop_table("projects")

    # Users and workers
    op.drop_table("users")
    op.drop_table("workers")
    op.drop_table("companies")

    # Reference tables
    op.drop_table("ppe_types")
    op.drop_table("material_categories")
    op.drop_table("construction_stages")
    op.drop_table("trades")
