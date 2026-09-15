"""
app/api/v1/daily_logs.py — Daily log retrieval, review lifecycle, AI generation.

Endpoints (matching docs/NEXT_SPRINT.md §2):
    GET  /daily-logs/{id}                 full log + all child tables
    POST /daily-logs/{id}/submit          draft -> under_review
    POST /daily-logs/{id}/approve         under_review -> approved (PM/owner only)
    POST /daily-logs/{id}/reject          under_review -> rejected, notes required (PM/owner only)
    POST /daily-logs/{id}/generate        re-run the 4 AI documents for this log
    GET  /daily-logs/{id}/outputs         list the current generation outputs for this log
    POST /daily-logs/{id}/outputs/{output_id}/mark-sent   track that a document was sent
    GET  /daily-logs/{id}/outputs/{output_id}/pdf         export a document as a PDF (Sprint 10)

Review-lifecycle business logic (the draft -> under_review -> approved |
rejected state machine, including "cannot approve an already-approved log")
lives entirely in DailyLogRepository (Sprint 6, frozen) — this router
translates ValueError (raised on an illegal transition) into HTTP 409 via
the global exception handler (app/middleware/exception_handlers.py). The
router itself contains no state-machine logic.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_app_settings, get_db, require_permission
from app.core.config import Settings
from app.core.permissions import Permission
from app.core.rate_limit import (
    RateLimiter,
    enforce_ai_generation_rate_limit,
    get_rate_limiter,
)
from app.schemas.daily_log import ApproveLogRequest, DailyLogRead, RejectLogRequest
from app.schemas.envelope import APIResponse, success_response
from app.schemas.generation import GenerationOutputRead, TriggerGenerationResponseData
from database.repositories.daily_log import DailyLogRepository
from database.repositories.generation import GenerationRepository
from database.repositories.inventory import InventoryRepository
from database.repositories.schedule import ScheduleRepository
from database.repositories.tenant import TenantContext

logger = logging.getLogger("app.api.daily_logs")

router = APIRouter(prefix="/daily-logs", tags=["Daily Logs"])


def _get_log_or_404(repo: DailyLogRepository, log_id: uuid.UUID, *, tenant: TenantContext):
    """Tenant-scoped log lookup — the single choke point every route in
    this file uses, so scoping applies uniformly without each route
    needing to remember it. Returns 404 for both "no such log" and "log
    belongs to a different company" — see database/repositories/tenant.py
    for why these are deliberately indistinguishable to the client."""
    log = repo.get_with_children_scoped(log_id, tenant=tenant)
    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Daily log not found."
        )
    return log


def _num(value):
    """Numeric columns come back as Decimal from PostgreSQL; the
    generation prompts format them into prose, and Decimal renders as
    "Decimal('40.00')" in an f-string. Convert to float, preserving None."""
    return float(value) if value is not None else None


def _rebuild_extracted_log(log) -> dict:
    """Rebuild the extracted_log-shaped dict the generation services
    expect, from a persisted DailyLog row and its child tables.

    This is the read-path inverse of
    DailyLogRepository.create_from_extraction_result()'s write path, and
    every key here mirrors a key that method reads — see that method for
    the authoritative field names.

    Why this must stay complete: run_pipeline() (app/services/
    pipeline_service.py) passes the FULL extraction output to
    generate_all(), while this route reconstructs it from the database.
    If the two diverge, a regenerated document is quietly thinner than
    the one the pipeline produced from the same log — the same content,
    same prompts, same model, but missing whole categories of input. An
    earlier version of this function omitted delays, equipment, hazards,
    inspections, materials delivered/required, work-in-progress and
    trades-on-site entirely, so regenerating a log that recorded a
    two-hour weather delay produced a daily report with no delay section
    at all.
    """
    return {
        "log_id": str(log.id),
        "log_date": log.log_date.isoformat(),
        "log_source": log.log_source,
        "review_status": log.review_status,
        "raw_transcript": log.raw_transcript,
        "transcript_confidence": _num(log.transcript_confidence),
        "current_stage": log.current_stage,
        "active_stages": log.active_stages,
        "stage_completion_percent": _num(log.stage_completion_percent),
        "overall_project_completion_percent": _num(
            log.overall_project_completion_percent
        ),
        "weather": log.weather,
        "workforce": {
            "total_workers_present": log.total_workers_present,
            "total_workers_scheduled": log.total_workers_scheduled,
            "total_man_hours_worked": _num(log.total_man_hours_worked),
            "late_arrivals": log.late_arrivals,
            "absences": log.absences,
            "visitors": log.visitors,
            "workforce_notes": log.workforce_notes,
            "trades_on_site": [
                {
                    "trade": t.trade,
                    "workers_count": t.workers_count,
                    "foreman_name": t.foreman_name,
                    "subcontractor_company": t.subcontractor_company,
                    "hours_worked": _num(t.hours_worked),
                    "notes": t.notes,
                }
                for t in log.trades_on_site
            ],
        },
        "work_completed": [
            {
                "task_description": w.task_description,
                "trade": w.trade,
                "location_on_site": w.location_on_site,
                "quantity_completed": _num(w.quantity_completed),
                "unit_of_measure": w.unit_of_measure,
                "task_completion_percent": _num(w.task_completion_percent),
                "notes": w.notes,
            }
            for w in log.work_items
        ],
        "work_in_progress": [
            {
                "task_description": w.task_description,
                "trade": w.trade,
                "location_on_site": w.location_on_site,
                "current_completion_percent": _num(w.current_completion_percent),
                "expected_completion_date": (
                    w.expected_completion_date.isoformat()
                    if w.expected_completion_date
                    else None
                ),
                "blocking_issues": w.blocking_issues,
            }
            for w in log.work_in_progress
        ],
        "materials": {
            "used_today": [
                {
                    "material_name": m.material_name,
                    "category": m.category,
                    "quantity_used": _num(m.quantity_used),
                    "unit": m.unit,
                    "waste_quantity": _num(m.waste_quantity),
                    "unit_cost_usd": _num(m.unit_cost_usd),
                    "supplier": m.supplier,
                    "notes": m.notes,
                }
                for m in log.materials_used
            ],
            "delivered_today": [
                {
                    "material_name": m.material_name,
                    "quantity_delivered": _num(m.quantity_delivered),
                    "unit": m.unit,
                    "supplier": m.supplier,
                    "delivery_condition": m.delivery_condition,
                    "purchase_order_number": m.purchase_order_number,
                    "notes": m.notes,
                }
                for m in log.materials_delivered
            ],
            "required_for_tomorrow": [
                {
                    "material_name": m.material_name,
                    "quantity_needed": _num(m.quantity_needed),
                    "unit": m.unit,
                    "urgency": m.urgency,
                    "notes": m.notes,
                }
                for m in log.materials_required
            ],
            "shortage_flags": log.shortage_flags,
        },
        "equipment": [
            {
                "equipment_name": e.equipment_name,
                "equipment_type": e.equipment_type,
                "is_rented": e.is_rented,
                "hours_used": _num(e.hours_used),
                "operator": e.operator,
                "equipment_condition": e.equipment_condition,
                "maintenance_issues": e.maintenance_issues,
                "fuel_consumed_liters": _num(e.fuel_consumed_liters),
            }
            for e in log.equipment
        ],
        "safety": {
            "safety_meeting_conducted": log.safety_meeting_conducted,
            "safety_meeting_duration_minutes": log.safety_meeting_duration_minutes,
            "safety_meeting_topics": log.safety_meeting_topics,
            "ppe_compliance_observed": log.ppe_compliance_observed,
            "ppe_required_today": log.ppe_required_today,
            "safety_notes": log.safety_notes,
            "incidents": [
                {
                    "incident_type": i.incident_type,
                    "description": i.description,
                    "worker_involved": i.worker_involved,
                    "time_of_incident": i.time_of_incident,
                    "body_part_affected": i.body_part_affected,
                    "osha_recordable": i.osha_recordable,
                    "medical_treatment_required": i.medical_treatment_required,
                    "incident_reported_to": i.incident_reported_to,
                    "corrective_actions": i.corrective_actions,
                }
                for i in log.safety_incidents
            ],
            "hazards_identified": [
                {
                    "hazard_type": h.hazard_type,
                    "location": h.location,
                    "description": h.description,
                    "severity": h.severity,
                    "corrective_action": h.corrective_action,
                    "corrective_action_completed": h.corrective_action_completed,
                }
                for h in log.hazards
            ],
        },
        "delays": [
            {
                "delay_type": d.delay_type,
                "description": d.description,
                "hours_lost": _num(d.hours_lost),
                "workers_affected": d.workers_affected,
                "tasks_affected": d.tasks_affected,
                "schedule_impact": d.schedule_impact,
                "days_lost_to_schedule": _num(d.days_lost_to_schedule),
                "resolution_action": d.resolution_action,
                "delay_resolved": d.delay_resolved,
                "responsible_party": d.responsible_party,
            }
            for d in log.delays
        ],
        "inspections": [
            {
                "inspection_type": i.inspection_type,
                "inspector_name": i.inspector_name,
                "inspection_authority": i.inspection_authority,
                "inspection_time": i.inspection_time,
                "result": i.result,
                "corrections_required": i.corrections_required,
                "next_inspection_date": (
                    i.next_inspection_date.isoformat()
                    if i.next_inspection_date
                    else None
                ),
                "inspection_notes": i.inspection_notes,
            }
            for i in log.inspections
        ],
        "tomorrow_plan": log.tomorrow_plan,
        "client_communication": log.client_communication,
        "attachments": log.attachments,
        "financials": log.financials,
    }


@router.get(
    "/{log_id}",
    response_model=APIResponse[DailyLogRead],
    summary="Get a daily log with all child records",
)
def get_daily_log(
    log_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.DAILY_LOG_READ)),
) -> APIResponse[DailyLogRead]:
    repo = DailyLogRepository(session)
    tenant = TenantContext.from_current_user(user)
    log = _get_log_or_404(repo, log_id, tenant=tenant)
    return success_response(DailyLogRead.model_validate(log), message="Daily log retrieved.")


@router.post(
    "/{log_id}/submit",
    response_model=APIResponse[DailyLogRead],
    summary="Submit a draft log for review",
)
def submit_for_review(
    log_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.DAILY_LOG_SUBMIT)),
) -> APIResponse[DailyLogRead]:
    repo = DailyLogRepository(session)
    tenant = TenantContext.from_current_user(user)
    log = _get_log_or_404(repo, log_id, tenant=tenant)
    repo.submit_for_review(log)  # raises ValueError -> HTTP 409 if not draft
    return success_response(DailyLogRead.model_validate(log), message="Submitted for review.")


@router.post(
    "/{log_id}/approve",
    response_model=APIResponse[DailyLogRead],
    summary="Approve a log under review (owner/project_manager only)",
)
def approve_log(
    log_id: uuid.UUID,
    body: ApproveLogRequest,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.DAILY_LOG_APPROVE)),
) -> APIResponse[DailyLogRead]:
    repo = DailyLogRepository(session)
    tenant = TenantContext.from_current_user(user)
    log = _get_log_or_404(repo, log_id, tenant=tenant)
    repo.approve(log, reviewer_id=user.user_id, notes=body.notes)

    # Commit the approval on its own, in its own transaction, BEFORE
    # attempting the schedule update below. get_db()'s session otherwise
    # only auto-commits once at the very end of the request and rolls
    # back everything in the transaction on any exception (the exact
    # mechanism behind the Sprint 8 account-lockout bug documented in
    # docs/DECISIONS.md) — without this explicit commit here, a failure
    # in the best-effort schedule update below would silently undo the
    # approval too, even though the response already promises it
    # succeeded.
    session.commit()
    session.refresh(log)

    # Sprint 11, Deliverable 4: populate the project's schedule with this
    # approval's real progress -- synchronous (per the design decision
    # documented in docs/PROJECT_STATE.md's Sprint 11 section: this is a
    # handful of row reads/writes, not worth Celery's async overhead the
    # way the multi-minute audio pipeline is). Deliberately best-effort
    # and fully isolated from the approval above (already committed): a
    # project with no schedule yet or a stage_id with no matching task
    # returns None rather than raising, and any other unexpected error
    # here is caught, logged, and rolled back on its own — never allowed
    # to affect the approval this endpoint already promised the caller.
    try:
        ScheduleRepository(session).record_actual_progress(
            log.project_id,
            stage_id=log.current_stage,
            log_date=log.log_date,
            stage_completion_percent=(
                float(log.stage_completion_percent)
                if log.stage_completion_percent is not None
                else None
            ),
            tenant=tenant,
        )
        session.commit()
    except Exception:
        logger.warning(
            "approve_log: schedule progress update failed for log_id=%s "
            "(approval itself already committed) — see traceback",
            log_id, exc_info=True,
        )
        session.rollback()

    # Sprint 12, Deliverables 2 + 3: reconcile project inventory from this
    # log's materials_used/materials_delivered, then check for any item
    # that dropped to/below its reorder_point and auto-create a draft PO.
    # Same isolation discipline as the schedule update above -- its own
    # commit/rollback, never allowed to affect the already-committed
    # approval, and best-effort (a project with no inventory tracking
    # configured yet is not an error, just nothing to reconcile).
    try:
        inv_repo = InventoryRepository(session)
        touched = inv_repo.record_material_consumption_from_log(
            log.project_id,
            materials_used=log.materials_used,
            materials_delivered=log.materials_delivered,
        )
        inv_repo.check_and_create_reorder_purchase_orders(touched)
        session.commit()
    except Exception:
        logger.warning(
            "approve_log: inventory reconciliation failed for log_id=%s "
            "(approval itself already committed) — see traceback",
            log_id, exc_info=True,
        )
        session.rollback()

    return success_response(DailyLogRead.model_validate(log), message="Log approved.")


@router.post(
    "/{log_id}/reject",
    response_model=APIResponse[DailyLogRead],
    summary="Reject a log under review (owner/project_manager only)",
)
def reject_log(
    log_id: uuid.UUID,
    body: RejectLogRequest,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.DAILY_LOG_REJECT)),
) -> APIResponse[DailyLogRead]:
    repo = DailyLogRepository(session)
    tenant = TenantContext.from_current_user(user)
    log = _get_log_or_404(repo, log_id, tenant=tenant)
    repo.reject(log, reviewer_id=user.user_id, notes=body.notes)
    return success_response(DailyLogRead.model_validate(log), message="Log rejected.")


@router.post(
    "/{log_id}/generate",
    response_model=APIResponse[TriggerGenerationResponseData],
    summary="Generate (or regenerate) the 4 AI documents for this log",
    description=(
        "Runs synchronously (unlike audio upload) — generation for one "
        "already-extracted log typically completes in a few seconds, so "
        "there is no need for background-task polling here."
    ),
)
def trigger_generation(
    log_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.DAILY_LOG_GENERATE)),
    settings: Settings = Depends(get_app_settings),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> APIResponse[TriggerGenerationResponseData]:
    from generation.config import GenerationConfig
    from generation.manager import AIServiceManager

    enforce_ai_generation_rate_limit(
        rate_limiter, user_id=user.user_id, settings=settings
    )

    log_repo = DailyLogRepository(session)
    tenant = TenantContext.from_current_user(user)
    log = _get_log_or_404(log_repo, log_id, tenant=tenant)

    log_dict = _rebuild_extracted_log(log)

    manager = AIServiceManager(config=GenerationConfig.from_env())
    gen_result = manager.generate_all(log_dict)

    outputs = [
        gen_result.daily_report, gen_result.customer_update,
        gen_result.safety_talk, gen_result.material_reminder,
    ]
    gen_repo = GenerationRepository(session)
    saved_types = []
    for output in outputs:
        if output and output.content:
            gen_repo.create_from_service_output(log_id, output)
            saved_types.append(output.service_type.value)

    return success_response(
        TriggerGenerationResponseData(
            daily_log_id=log_id, outputs_generated=len(saved_types), service_types=saved_types,
        ),
        message=f"Generated {len(saved_types)} document(s).",
    )


@router.get(
    "/{log_id}/outputs",
    response_model=APIResponse[list[GenerationOutputRead]],
    summary="List the current AI-generated documents for this log",
    description=(
        "Returns the most recent output per document type (daily report, "
        "customer update, safety talk, material reminder) — the current "
        "set a client should display, not the full regeneration history. "
        "See GenerationRepository.list_latest_for_log()."
    ),
)
def list_generation_outputs(
    log_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.DAILY_LOG_READ)),
) -> APIResponse[list[GenerationOutputRead]]:
    log_repo = DailyLogRepository(session)
    tenant = TenantContext.from_current_user(user)
    _get_log_or_404(log_repo, log_id, tenant=tenant)  # 404 if not found or wrong tenant

    gen_repo = GenerationRepository(session)
    outputs = gen_repo.list_latest_for_log(log_id)
    return success_response(
        [GenerationOutputRead.model_validate(o) for o in outputs],
        message=f"Found {len(outputs)} output(s).",
    )


@router.post(
    "/{log_id}/outputs/{output_id}/mark-sent",
    response_model=APIResponse[GenerationOutputRead],
    summary="Mark a generated document as sent to the client",
    description=(
        "Sprint 10: tracks that a PM confirmed a document (typically the "
        "customer update) was sent — GenerationOutput.is_sent/sent_at "
        "already existed since Sprint 6 but nothing set them until now. "
        "This does NOT send anything itself — no client contact email "
        "field exists yet to send to (see docs/NEXT_SPRINT.md Deliverable "
        "3). It only records that sending already happened, e.g. via the "
        "PM's own email client. Idempotent: marking an already-sent "
        "output sent again just returns it unchanged, not an error."
    ),
)
def mark_output_sent(
    log_id: uuid.UUID,
    output_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.DAILY_LOG_SEND_OUTPUT)),
) -> APIResponse[GenerationOutputRead]:
    log_repo = DailyLogRepository(session)
    tenant = TenantContext.from_current_user(user)
    _get_log_or_404(log_repo, log_id, tenant=tenant)  # 404 if not found or wrong tenant

    gen_repo = GenerationRepository(session)
    output = gen_repo.get_by_id(output_id)
    # GenerationOutput has no direct company_id column — tenant scoping
    # comes from confirming log_id above, then confirming THIS output
    # actually belongs to that (already tenant-verified) log, exactly
    # the same two-step pattern _get_log_or_404 exists to short-circuit
    # for every other daily-logs sub-resource route.
    if output is None or output.daily_log_id != log_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generated document not found for this log.",
        )

    was_already_sent = output.is_sent
    if not was_already_sent:
        output = gen_repo.mark_sent(output)
    return success_response(
        GenerationOutputRead.model_validate(output),
        message="Already marked as sent." if was_already_sent else "Marked as sent.",
    )


@router.get(
    "/{log_id}/outputs/{output_id}/pdf",
    summary="Export a generated document as a PDF",
    description=(
        "Sprint 10, scoped to safety_talk only (per docs/NEXT_SPRINT.md "
        "Deliverable 4 — 'scope narrowly ... generalizing to all 4 output "
        "types is a natural follow-up, not required now'). Returns the "
        "raw PDF bytes with a file-download Content-Disposition header, "
        "not the standard APIResponse envelope — a binary file has no "
        "natural JSON `data` field to sit inside."
    ),
    responses={200: {"content": {"application/pdf": {}}}},
)
def export_output_pdf(
    log_id: uuid.UUID,
    output_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.DAILY_LOG_READ)),
) -> Response:
    from app.services.pdf_export import render_markdown_pdf

    log_repo = DailyLogRepository(session)
    tenant = TenantContext.from_current_user(user)
    log = _get_log_or_404(log_repo, log_id, tenant=tenant)

    gen_repo = GenerationRepository(session)
    output = gen_repo.get_by_id(output_id)
    if output is None or output.daily_log_id != log_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generated document not found for this log.",
        )
    if output.service_type != "safety_talk":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "PDF export is only available for safety_talk documents "
                f"in this sprint (got '{output.service_type}')."
            ),
        )

    pdf_bytes = render_markdown_pdf(
        f"Safety Toolbox Talk — {log.log_date.isoformat()}", output.content,
    )
    filename = f"safety-talk-{log.log_date.isoformat()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
