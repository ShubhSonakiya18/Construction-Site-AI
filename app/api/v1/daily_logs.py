"""
app/api/v1/daily_logs.py — Daily log retrieval, review lifecycle, AI generation.

Endpoints (matching docs/NEXT_SPRINT.md §2):
    GET  /daily-logs/{id}                 full log + all child tables
    POST /daily-logs/{id}/submit          draft -> under_review
    POST /daily-logs/{id}/approve         under_review -> approved (PM/owner only)
    POST /daily-logs/{id}/reject          under_review -> rejected, notes required (PM/owner only)
    POST /daily-logs/{id}/generate        re-run the 4 AI documents for this log
    GET  /daily-logs/{id}/outputs         list generation outputs for this log

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
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, get_db, require_role
from app.schemas.daily_log import ApproveLogRequest, DailyLogRead, RejectLogRequest
from app.schemas.envelope import APIResponse, success_response
from app.schemas.generation import GenerationOutputRead, TriggerGenerationResponseData
from database.repositories.daily_log import DailyLogRepository
from database.repositories.generation import GenerationRepository

router = APIRouter(prefix="/daily-logs", tags=["Daily Logs"])


def _get_log_or_404(repo: DailyLogRepository, log_id: uuid.UUID):
    log = repo.get_with_children(log_id)
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
    user: CurrentUser = Depends(get_current_user),
) -> APIResponse[DailyLogRead]:
    repo = DailyLogRepository(session)
    log = _get_log_or_404(repo, log_id)
    return success_response(DailyLogRead.model_validate(log), message="Daily log retrieved.")


@router.post(
    "/{log_id}/submit",
    response_model=APIResponse[DailyLogRead],
    summary="Submit a draft log for review",
)
def submit_for_review(
    log_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> APIResponse[DailyLogRead]:
    repo = DailyLogRepository(session)
    log = _get_log_or_404(repo, log_id)
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
    user: CurrentUser = Depends(require_role("owner", "project_manager")),
) -> APIResponse[DailyLogRead]:
    repo = DailyLogRepository(session)
    log = _get_log_or_404(repo, log_id)
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
    user: CurrentUser = Depends(require_role("owner", "project_manager")),
) -> APIResponse[DailyLogRead]:
    repo = DailyLogRepository(session)
    log = _get_log_or_404(repo, log_id)
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
    user: CurrentUser = Depends(get_current_user),
) -> APIResponse[TriggerGenerationResponseData]:
    from generation.config import GenerationConfig
    from generation.manager import AIServiceManager

    log_repo = DailyLogRepository(session)
    log = _get_log_or_404(log_repo, log_id)

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
    summary="List all AI-generated documents for this log",
)
def list_generation_outputs(
    log_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> APIResponse[list[GenerationOutputRead]]:
    log_repo = DailyLogRepository(session)
    _get_log_or_404(log_repo, log_id)  # 404 if the log itself doesn't exist

    gen_repo = GenerationRepository(session)
    outputs = gen_repo.list_for_log(log_id)
    return success_response(
        [GenerationOutputRead.model_validate(o) for o in outputs],
        message=f"Found {len(outputs)} output(s).",
    )
