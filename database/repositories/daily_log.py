"""
database/repositories/daily_log.py — DailyLog repository.

This is the most used repository in the system. Every Sprint 7 API request
that involves a daily log (create, review, approve, regenerate) goes through
DailyLogRepository.

Key methods:
    create_from_extraction_result() — Sprint 4 integration point
    get_with_children()            — returns a DailyLog + all child rows in one query
    approve() / reject()           — review lifecycle state transitions
    list_for_date_range()          — Sprint 7 dashboard API (recent logs)
    get_for_generation()           — Sprint 5 integration point (load log for AI services)
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from database.models.daily_log import DailyLog
from database.models.log_items import (
    LogDelay,
    LogEquipment,
    LogHazard,
    LogInspection,
    LogMaterialDelivered,
    LogMaterialRequired,
    LogMaterialUsed,
    LogSafetyIncident,
    LogTradeOnSite,
    LogWorkInProgress,
    LogWorkItem,
)
from database.repositories.tenant import TenantContext, TenantScopedRepository


class DailyLogRepository(TenantScopedRepository[DailyLog]):
    """Repository for DailyLog and all its normalized child tables.

    Tenant scoping (Sprint 8, Subsystem 3): DailyLog has no direct
    company_id column — company is reached via project_id -> Project.
    company_id. get_with_children_scoped() is the tenant-safe read path
    every router should use; get_with_children() (unscoped) remains for
    Sprint 1-7 callers (CLI scripts, the pipeline service, which already
    knows the correct project_id from the AudioFile it's processing and
    has no HTTP-authenticated caller to scope against).
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session, DailyLog)

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_with_children(self, log_id: UUID) -> Optional[DailyLog]:
        """Return a DailyLog with all child tables eagerly loaded.

        UNSCOPED — does not filter by company. Safe for Sprint 1-7
        non-HTTP callers (pipeline_service.py, CLI scripts, tests) that
        already know the log belongs to the right tenant by construction.
        HTTP routers must use get_with_children_scoped() instead — see
        that method's docstring.
        """
        stmt = (
            select(DailyLog)
            .where(DailyLog.id == log_id)
            .where(DailyLog.deleted_at.is_(None))
            .options(
                selectinload(DailyLog.trades_on_site),
                selectinload(DailyLog.work_items),
                selectinload(DailyLog.work_in_progress),
                selectinload(DailyLog.materials_used),
                selectinload(DailyLog.materials_delivered),
                selectinload(DailyLog.materials_required),
                selectinload(DailyLog.equipment),
                selectinload(DailyLog.safety_incidents),
                selectinload(DailyLog.hazards),
                selectinload(DailyLog.delays),
                selectinload(DailyLog.inspections),
            )
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_with_children_scoped(
        self, log_id: UUID, *, tenant: TenantContext
    ) -> Optional[DailyLog]:
        """Return a DailyLog with all child tables eagerly loaded, ONLY if
        it belongs to tenant.company_id — the tenant-safe replacement for
        get_with_children() at every HTTP entry point.

        Returns None (not a raise) for both "no such log" and "log exists
        but belongs to a different company" — the caller (a router) turns
        None into a 404, and the two cases are deliberately
        indistinguishable to the client. See module docstring in
        database/repositories/tenant.py for the full rationale (matches
        this codebase's existing account-enumeration-avoidance posture).
        """
        from database.models.project import Project

        stmt = (
            select(DailyLog)
            .join(Project, DailyLog.project_id == Project.id)
            .where(DailyLog.id == log_id)
            .where(DailyLog.deleted_at.is_(None))
            .where(Project.company_id == tenant.company_id)
            .options(
                selectinload(DailyLog.trades_on_site),
                selectinload(DailyLog.work_items),
                selectinload(DailyLog.work_in_progress),
                selectinload(DailyLog.materials_used),
                selectinload(DailyLog.materials_delivered),
                selectinload(DailyLog.materials_required),
                selectinload(DailyLog.equipment),
                selectinload(DailyLog.safety_incidents),
                selectinload(DailyLog.hazards),
                selectinload(DailyLog.delays),
                selectinload(DailyLog.inspections),
            )
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_with_children_cross_tenant(
        self, log_id: UUID, *, tenant: TenantContext, request_id: Optional[str] = None
    ) -> Optional[DailyLog]:
        """System Admin bypass: return a DailyLog regardless of which
        company it belongs to. ONLY reachable from a route already gated
        by Permission.COMPANY_READ_ANY (require_permission() at the
        router layer) — see database/repositories/tenant.py module
        docstring. Writes a mandatory AuditLog entry before returning.
        """
        log = self.get_with_children(log_id)
        from database.models.project import Project
        from database.repositories.project import ProjectRepository

        target_company_id = None
        if log is not None:
            project = ProjectRepository(self._session).get_by_id(log.project_id)
            target_company_id = project.company_id if project is not None else None

        self._audit_cross_tenant_access(
            tenant_context_actor=tenant,
            target_company_id=target_company_id,
            entity_type="daily_log",
            entity_id=log_id,
            action="get_with_children_cross_tenant",
            request_id=request_id,
        )
        return log

    def get_by_project_date(
        self, project_id: UUID, log_date: date
    ) -> Optional[DailyLog]:
        """Return the log for a specific project on a specific date.

        Enforces the UniqueConstraint uq_daily_logs_project_date.
        """
        stmt = (
            select(DailyLog)
            .where(DailyLog.project_id == project_id)
            .where(DailyLog.log_date == log_date)
            .where(DailyLog.deleted_at.is_(None))
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def list_by_project(
        self,
        project_id: UUID,
        *,
        status: Optional[str] = None,
        limit: int = 30,
        offset: int = 0,
    ) -> list[DailyLog]:
        """List daily logs for a project, newest first.

        UNSCOPED — see get_with_children()'s docstring for the same
        caveat. HTTP routers must use list_by_project_scoped().
        """
        stmt = (
            select(DailyLog)
            .where(DailyLog.project_id == project_id)
            .where(DailyLog.deleted_at.is_(None))
        )
        if status is not None:
            stmt = stmt.where(DailyLog.review_status == status)
        stmt = stmt.order_by(DailyLog.log_date.desc()).limit(limit).offset(offset)
        return list(self._session.execute(stmt).scalars().all())

    def list_by_project_scoped(
        self,
        project_id: UUID,
        *,
        tenant: TenantContext,
        status: Optional[str] = None,
        limit: int = 30,
        offset: int = 0,
    ) -> list[DailyLog]:
        """Tenant-safe replacement for list_by_project(). Returns an empty
        list (not a raise, not a 403) if project_id belongs to a
        different company than tenant.company_id — the caller (router)
        then reports "0 logs found," indistinguishable from a project
        with genuinely no logs. Whether the project itself exists at all
        is a separate 404 concern the router should check first via
        ProjectRepository.get_by_id_scoped()."""
        from database.models.project import Project

        stmt = (
            select(DailyLog)
            .join(Project, DailyLog.project_id == Project.id)
            .where(DailyLog.project_id == project_id)
            .where(DailyLog.deleted_at.is_(None))
            .where(Project.company_id == tenant.company_id)
        )
        if status is not None:
            stmt = stmt.where(DailyLog.review_status == status)
        stmt = stmt.order_by(DailyLog.log_date.desc()).limit(limit).offset(offset)
        return list(self._session.execute(stmt).scalars().all())

    def list_pending_review(self, company_id: UUID) -> list[DailyLog]:
        """Return all logs in 'under_review' status for a company.

        Used by Sprint 7 API: PM dashboard shows logs awaiting approval.
        """
        stmt = (
            select(DailyLog)
            .join(DailyLog.project)
            .where(DailyLog.deleted_at.is_(None))
            .where(DailyLog.review_status == "under_review")
            .order_by(DailyLog.log_date.desc())
        )
        from database.models.project import Project
        stmt = stmt.where(Project.company_id == company_id)
        return list(self._session.execute(stmt).scalars().all())

    def list_approved_for_generation(
        self, project_id: UUID, limit: int = 5
    ) -> list[DailyLog]:
        """Return recent approved logs ready for AI generation input.

        Sprint 5 generation/ package receives the most recent approved logs
        as context. This method returns them newest-first.
        """
        stmt = (
            select(DailyLog)
            .where(DailyLog.project_id == project_id)
            .where(DailyLog.deleted_at.is_(None))
            .where(DailyLog.review_status == "approved")
            .order_by(DailyLog.log_date.desc())
            .limit(limit)
        )
        return list(self._session.execute(stmt).scalars().all())

    # ── Review Lifecycle ──────────────────────────────────────────────────────

    def submit_for_review(self, log: DailyLog) -> DailyLog:
        """Transition a draft log to under_review status."""
        if log.review_status != "draft":
            raise ValueError(
                f"Cannot submit log {log.id} for review: "
                f"current status is '{log.review_status}' (must be 'draft')"
            )
        log.review_status = "under_review"
        self._session.flush()
        return log

    def approve(
        self, log: DailyLog, reviewer_id: UUID, notes: Optional[str] = None
    ) -> DailyLog:
        """Approve a log under review."""
        if log.review_status not in ("under_review", "draft"):
            raise ValueError(
                f"Cannot approve log {log.id}: "
                f"current status is '{log.review_status}'"
            )
        log.review_status = "approved"
        log.reviewed_by_id = reviewer_id
        log.reviewed_at = datetime.now(timezone.utc)
        if notes:
            log.review_notes = notes
        self._session.flush()
        return log

    def reject(
        self, log: DailyLog, reviewer_id: UUID, notes: str
    ) -> DailyLog:
        """Reject a log. Notes are required on rejection."""
        if not notes or not notes.strip():
            raise ValueError("Review notes are required when rejecting a log.")
        log.review_status = "rejected"
        log.reviewed_by_id = reviewer_id
        log.reviewed_at = datetime.now(timezone.utc)
        log.review_notes = notes
        self._session.flush()
        return log

    # ── Creation from Extraction Result ──────────────────────────────────────

    @staticmethod
    def _safe_uuid(value: object) -> "uuid.UUID":
        """Return a UUID from value, or a fresh uuid4 if value is absent/invalid."""
        if value is None:
            return uuid.uuid4()
        try:
            return uuid.UUID(str(value))
        except (ValueError, AttributeError):
            return uuid.uuid4()

    @staticmethod
    def resolve_log_date(extracted_log: dict) -> date:
        """Resolve extracted_log['log_date'] to a date, matching exactly the
        fallback logic create_from_extraction_result() uses at insert time.

        Extracted as a reusable static method (Sprint 7) so callers that
        need to know the log_date BEFORE calling create_from_extraction_result
        — e.g. app/services/pipeline_service.py pre-checking for a same-day
        duplicate — resolve the identical value the insert will use, rather
        than duplicating this fallback logic and risking drift.
        """
        log_date_raw = extracted_log.get("log_date")
        if isinstance(log_date_raw, str):
            try:
                return date.fromisoformat(log_date_raw)
            except ValueError:
                return date.today()
        elif isinstance(log_date_raw, date):
            return log_date_raw
        return date.today()

    def create_from_extraction_result(
        self,
        extracted_log: dict,
        project_id: UUID,
        *,
        audio_file_id: Optional[UUID] = None,
        foreman_id: Optional[UUID] = None,
        site_id: Optional[UUID] = None,
        created_by_id: Optional[UUID] = None,
    ) -> DailyLog:
        """Persist a Sprint 4 ExtractionResult.extracted_log dict to the database.

        This is the primary integration point between Sprint 4 (extraction/)
        and Sprint 6 (database/). The extracted_log dict follows the
        ConstructionDailyLog v1.0.0 schema.

        Child tables (work_items, delays, etc.) are created automatically from
        the nested arrays in the extracted_log dict.

        Returns the newly created DailyLog with all children attached.
        """
        # ── Core log row ──────────────────────────────────────────────────────
        log_date_val = self.resolve_log_date(extracted_log)

        log = DailyLog(
            id=self._safe_uuid(extracted_log.get("log_id")),
            project_id=project_id,
            site_id=site_id,
            audio_file_id=audio_file_id,
            foreman_id=foreman_id,
            log_date=log_date_val,
            log_source=extracted_log.get("log_source") or "voice_recording",
            review_status=extracted_log.get("review_status") or "draft",
            raw_transcript=extracted_log.get("raw_transcript"),
            transcript_confidence=extracted_log.get("transcript_confidence"),
            current_stage=extracted_log.get("current_stage") or "site_preparation",
            active_stages=extracted_log.get("active_stages"),
            stage_completion_percent=extracted_log.get("stage_completion_percent"),
            overall_project_completion_percent=extracted_log.get("overall_project_completion_percent"),
            weather=extracted_log.get("weather"),
            total_workers_present=(extracted_log.get("workforce") or {}).get("total_workers_present") or 0,
            total_workers_scheduled=(extracted_log.get("workforce") or {}).get("total_workers_scheduled"),
            total_man_hours_worked=(extracted_log.get("workforce") or {}).get("total_man_hours_worked"),
            late_arrivals=(extracted_log.get("workforce") or {}).get("late_arrivals"),
            absences=(extracted_log.get("workforce") or {}).get("absences"),
            visitors=(extracted_log.get("workforce") or {}).get("visitors"),
            workforce_notes=(extracted_log.get("workforce") or {}).get("workforce_notes"),
            safety_meeting_conducted=(extracted_log.get("safety") or {}).get("safety_meeting_conducted") or False,
            safety_meeting_duration_minutes=(extracted_log.get("safety") or {}).get("safety_meeting_duration_minutes"),
            safety_meeting_topics=(extracted_log.get("safety") or {}).get("safety_meeting_topics"),
            ppe_compliance_observed=(extracted_log.get("safety") or {}).get("ppe_compliance_observed"),
            ppe_required_today=(extracted_log.get("safety") or {}).get("ppe_required_today"),
            safety_notes=(extracted_log.get("safety") or {}).get("safety_notes"),
            shortage_flags=(extracted_log.get("materials") or {}).get("shortage_flags"),
            tomorrow_plan=extracted_log.get("tomorrow_plan"),
            client_communication=extracted_log.get("client_communication"),
            attachments=extracted_log.get("attachments"),
            financials=extracted_log.get("financials"),
            created_by_id=created_by_id,
        )
        self._session.add(log)
        self._session.flush()  # get log.id before creating children

        # ── Child tables ──────────────────────────────────────────────────────
        workforce = extracted_log.get("workforce") or {}
        for trade_entry in workforce.get("trades_on_site", []) or []:
            self._session.add(LogTradeOnSite(
                daily_log_id=log.id,
                trade=trade_entry.get("trade") or "other",
                workers_count=trade_entry.get("workers_count") or 0,
                foreman_name=trade_entry.get("foreman_name"),
                subcontractor_company=trade_entry.get("subcontractor_company"),
                hours_worked=trade_entry.get("hours_worked"),
                notes=trade_entry.get("notes"),
            ))

        for item in extracted_log.get("work_completed", []) or []:
            self._session.add(LogWorkItem(
                daily_log_id=log.id,
                task_description=item.get("task_description") or "",
                trade=item.get("trade") or "other",
                location_on_site=item.get("location_on_site"),
                quantity_completed=item.get("quantity_completed"),
                unit_of_measure=item.get("unit_of_measure"),
                task_completion_percent=item.get("task_completion_percent"),
                linked_schedule_task_id=item.get("linked_schedule_task_id"),
                notes=item.get("notes"),
            ))

        for item in extracted_log.get("work_in_progress", []) or []:
            self._session.add(LogWorkInProgress(
                daily_log_id=log.id,
                task_description=item.get("task_description") or "",
                trade=item.get("trade"),
                location_on_site=item.get("location_on_site"),
                current_completion_percent=item.get("current_completion_percent"),
                blocking_issues=item.get("blocking_issues"),
            ))

        materials = extracted_log.get("materials", {}) or {}
        for item in materials.get("used_today", []) or []:
            self._session.add(LogMaterialUsed(
                daily_log_id=log.id,
                material_name=item.get("material_name") or "",
                category=item.get("category"),
                quantity_used=item.get("quantity_used") or 0,
                unit=item.get("unit") or "each",
                waste_quantity=item.get("waste_quantity"),
                unit_cost_usd=item.get("unit_cost_usd"),
                supplier=item.get("supplier"),
                notes=item.get("notes"),
            ))

        for item in materials.get("delivered_today", []) or []:
            self._session.add(LogMaterialDelivered(
                daily_log_id=log.id,
                material_name=item.get("material_name") or "",
                quantity_delivered=item.get("quantity_delivered") or 0,
                unit=item.get("unit") or "each",
                supplier=item.get("supplier"),
                delivery_condition=item.get("delivery_condition"),
                purchase_order_number=item.get("purchase_order_number"),
                notes=item.get("notes"),
            ))

        for item in materials.get("required_for_tomorrow", []) or []:
            self._session.add(LogMaterialRequired(
                daily_log_id=log.id,
                material_name=item.get("material_name") or "",
                quantity_needed=item.get("quantity_needed") or 0,
                unit=item.get("unit") or "each",
                urgency=item.get("urgency") or "medium",
                notes=item.get("notes"),
            ))

        for item in extracted_log.get("equipment", []) or []:
            self._session.add(LogEquipment(
                daily_log_id=log.id,
                equipment_name=item.get("equipment_name") or "",
                equipment_type=item.get("equipment_type"),
                is_rented=item.get("is_rented"),
                hours_used=item.get("hours_used"),
                operator=item.get("operator"),
                equipment_condition=item.get("equipment_condition"),
                maintenance_issues=item.get("maintenance_issues"),
                fuel_consumed_liters=item.get("fuel_consumed_liters"),
            ))

        safety = extracted_log.get("safety", {}) or {}
        for item in safety.get("incidents", []) or []:
            self._session.add(LogSafetyIncident(
                daily_log_id=log.id,
                incident_type=item.get("incident_type") or "near_miss",
                description=item.get("description") or "",
                worker_involved=item.get("worker_involved"),
                time_of_incident=item.get("time_of_incident"),
                body_part_affected=item.get("body_part_affected"),
                osha_recordable=item.get("osha_recordable"),
                medical_treatment_required=item.get("medical_treatment_required"),
                incident_reported_to=item.get("incident_reported_to"),
                corrective_actions=item.get("corrective_actions"),
            ))

        for item in safety.get("hazards_identified", []) or []:
            self._session.add(LogHazard(
                daily_log_id=log.id,
                hazard_type=item.get("hazard_type") or "other",
                location=item.get("location"),
                description=item.get("description") or "",
                severity=item.get("severity") or "low",
                corrective_action=item.get("corrective_action"),
                corrective_action_completed=item.get("corrective_action_completed") or False,
            ))

        for item in extracted_log.get("delays", []) or []:
            self._session.add(LogDelay(
                daily_log_id=log.id,
                delay_type=item.get("delay_type") or "other",
                description=item.get("description") or "",
                hours_lost=item.get("hours_lost"),
                workers_affected=item.get("workers_affected"),
                tasks_affected=item.get("tasks_affected"),
                schedule_impact=item.get("schedule_impact"),
                days_lost_to_schedule=item.get("days_lost_to_schedule"),
                resolution_action=item.get("resolution_action"),
                delay_resolved=item.get("delay_resolved") or False,
                responsible_party=item.get("responsible_party"),
            ))

        for item in extracted_log.get("inspections", []) or []:
            self._session.add(LogInspection(
                daily_log_id=log.id,
                inspection_type=item.get("inspection_type") or "other",
                inspector_name=item.get("inspector_name"),
                inspection_authority=item.get("inspection_authority"),
                inspection_time=item.get("inspection_time"),
                result=item.get("result") or "pending",
                corrections_required=item.get("corrections_required"),
                inspection_notes=item.get("inspection_notes"),
            ))

        self._session.flush()
        return log
