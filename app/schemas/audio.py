"""app/schemas/audio.py — Request/response models for the audio upload resource."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AudioUploadResponseData(BaseModel):
    """Returned immediately by POST /audio/upload — the pipeline (transcribe
    -> extract -> persist -> generate) runs afterward as a background task,
    so this response only confirms the file was accepted and queued."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str
    processing_status: str
    project_id: Optional[UUID] = None
    created_at: datetime


class AudioStatusResponseData(BaseModel):
    """Returned by GET /audio/{id}/status — polled by the client until
    processing_status reaches 'complete' or 'failed'."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str
    processing_status: str
    is_valid: Optional[bool] = None
    validation_errors: Optional[list[str]] = None
    duration_seconds: Optional[float] = None
    daily_log_id: Optional[UUID] = None
    error_message: Optional[str] = None
