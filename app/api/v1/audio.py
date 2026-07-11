"""
app/api/v1/audio.py — POST /audio/upload, GET /audio/{id}/status.

Upload flow:
    1. Client POSTs a multipart/form-data audio file + project_id.
    2. This router validates the upload is present and saves it to disk
       under data/uploads/ (mirrors the file-storage design already
       documented in database/models/audio.py — "actual audio binary is
       stored on disk/object storage, DB row stores queryable metadata").
    3. An AudioFile row is created with processing_status="pending".
    4. app.services.pipeline_service.run_pipeline is queued via FastAPI's
       BackgroundTasks — it runs AFTER this response is already sent.
    5. The client receives the AudioFile id immediately and polls
       GET /audio/{id}/status until processing_status is "complete" or
       "failed".

Why FastAPI BackgroundTasks (not Celery) — Sprint 7 scope, Sprint 8 extension:
    See app/create_app.py and app/services/pipeline_service.py docstrings.
    In short: BackgroundTasks.add_task(run_pipeline, audio_file.id) is the
    one line that would become run_pipeline.delay(audio_file.id) when
    Celery is introduced — no other code changes.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_current_user, get_db
from app.schemas.audio import AudioStatusResponseData, AudioUploadResponseData
from app.schemas.envelope import APIResponse, success_response
from app.services.pipeline_service import run_pipeline
from database.models.audio import AudioFile
from database.repositories.audio import AudioRepository

logger = logging.getLogger("app.api.audio")

router = APIRouter(prefix="/audio", tags=["Audio"])

_UPLOAD_DIR = Path("data/uploads")
_ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm", ".mp4"}
_MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB, matches SPEECH_MAX_FILE_SIZE_MB default


@router.post(
    "/upload",
    response_model=APIResponse[AudioUploadResponseData],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a voice recording and start the AI pipeline",
    description=(
        "Accepts an audio file, saves it, and queues the full pipeline "
        "(transcribe -> extract -> save daily log -> generate 4 documents) "
        "as a background task. Returns immediately with the AudioFile id — "
        "poll GET /audio/{id}/status for progress."
    ),
)
async def upload_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    project_id: uuid.UUID | None = Form(default=None),
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> APIResponse[AudioUploadResponseData]:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No file provided."
        )

    extension = Path(file.filename).suffix.lower()
    if extension not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{extension}'. Allowed: {sorted(_ALLOWED_EXTENSIONS)}",
        )

    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid.uuid4()}{extension}"
    stored_path = _UPLOAD_DIR / stored_filename

    size_bytes = 0
    with stored_path.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size_bytes += len(chunk)
            if size_bytes > _MAX_UPLOAD_BYTES:
                out.close()
                stored_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds the {_MAX_UPLOAD_BYTES // (1024*1024)}MB limit.",
                )
            out.write(chunk)

    audio_repo = AudioRepository(session)
    audio_file = audio_repo.create(
        AudioFile(
            project_id=project_id,
            uploaded_by_id=user.user_id,
            original_filename=file.filename,
            stored_filename=stored_filename,
            file_path=str(stored_path),
            file_size_bytes=size_bytes,
            mime_type=file.content_type,
            format=extension.lstrip("."),
            processing_status="pending",
        )
    )
    audio_file_id = audio_file.id

    background_tasks.add_task(run_pipeline, audio_file_id)
    logger.info("Queued pipeline for audio_file_id=%s (%d bytes)", audio_file_id, size_bytes)

    return success_response(
        AudioUploadResponseData.model_validate(audio_file),
        message="Upload accepted. Processing has started.",
    )


@router.get(
    "/{audio_file_id}/status",
    response_model=APIResponse[AudioStatusResponseData],
    summary="Poll the processing status of an uploaded recording",
)
def get_audio_status(
    audio_file_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> APIResponse[AudioStatusResponseData]:
    audio_repo = AudioRepository(session)
    audio_file = audio_repo.get_by_id(audio_file_id)
    if audio_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found."
        )

    error_message = None
    if audio_file.processing_status == "failed" and audio_file.validation_errors:
        error_message = "; ".join(audio_file.validation_errors)

    daily_log_id = audio_file.daily_log.id if audio_file.daily_log else None

    data = AudioStatusResponseData(
        id=audio_file.id,
        original_filename=audio_file.original_filename,
        processing_status=audio_file.processing_status,
        is_valid=audio_file.is_valid,
        validation_errors=audio_file.validation_errors,
        duration_seconds=(
            float(audio_file.duration_seconds) if audio_file.duration_seconds else None
        ),
        daily_log_id=daily_log_id,
        error_message=error_message,
    )
    return success_response(data, message=f"Status: {audio_file.processing_status}")
