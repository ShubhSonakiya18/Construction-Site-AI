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
from database.repositories.tenant import TenantContext

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

    # Rebuild the extracted_log-shaped dict the generation services expect,
    # from the persisted DailyLog row. This is the read-path inverse of
    # DailyLogRepository.create_from_extraction_result()'s write path.
    log_dict = {
        "log_id": str(log.id),
        "log_date": log.log_date.isoformat(),
        "current_stage": log.current_stage,
        "overall_project_completion_percent": log.overall_project_completion_percent,
        "weather": log.weather,
        "workforce": {"total_workers_present": log.total_workers_present},
        "work_completed": [
            {"task_description": w.task_description, "trade": w.trade}
            for w in log.work_items
        ],
        "materials": {
            "used_today": [
                {"material_name": m.material_name, "quantity_used": float(m.quantity_used)}
                for m in log.materials_used
            ],
        },
        "safety": {"safety_notes": log.safety_notes},
        "tomorrow_plan": log.tomorrow_plan,
        "client_communication": log.client_communication,
    }

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
