"""
app/tasks/pipeline_tasks.py — Celery task wrapping the Sprint 7 audio pipeline.

Sprint 9. The actual pipeline logic lives entirely in
app.services.pipeline_service.run_pipeline() (Sprint 7, unchanged) — this
module is only the Celery integration point, per docs/BACKEND_ARCHITECTURE.md
§10's documented extension plan.

Why retry lives HERE and not inside run_pipeline():
    run_pipeline() already delegates to two Sprint 1-6 subsystems that have
    their OWN internal retry loops for transient failures — most relevantly
    ExtractionPipeline.extract() (extraction/pipeline.py), which retries the
    Groq call itself (config.max_retries, exponential backoff) before ever
    returning ExtractionResult.success=False. By the time run_pipeline()
    observes a stage failure, that failure has already survived N in-process
    retries — it is a considered, final result, not a raw transient error a
    Celery-level retry should blindly repeat. run_pipeline() also never
    raises (see its own docstring: every failure is captured onto
    AudioFile.processing_status instead), so there is no exception for
    Celery's autoretry_for to even catch on that path.

    What Celery-level retry protects against instead is the OUTER failure
    mode Sprint 7 didn't have a queue for: the worker process itself dying
    mid-task (OOM-killed loading a Whisper model, a Redis network blip, an
    unhandled bug) — cases where run_pipeline() never got the chance to
    mark AudioFile "failed" at all, and the row would otherwise sit stuck in
    "transcribing"/"extracting"/"generating" forever. bind=True +
    autoretry_for=(Exception,) with backoff catches exactly that: a task
    that dies unexpectedly gets re-queued a bounded number of times before
    giving up.

Why max_retries=3 with exponential backoff, not celery's default:
    Mirrors the retry shape already established in extraction/pipeline.py
    and generation/services/base_service.py (a handful of retries with
    growing delay) rather than introducing a fourth different retry
    philosophy into the codebase.
"""
from __future__ import annotations

import logging

from celery_app import celery_app

logger = logging.getLogger("app.tasks.pipeline")


@celery_app.task(
    bind=True,
    name="app.tasks.pipeline_tasks.run_pipeline_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
def run_pipeline_task(self, audio_file_id: str) -> None:
    """Celery entry point — audio_file_id is passed as str (Celery's JSON
    serializer does not carry UUID objects) and converted back here, the
    one adaptation run_pipeline() itself did not need to make.
    """
    from uuid import UUID

    from app.services.pipeline_service import run_pipeline

    logger.info(
        "run_pipeline_task: starting audio_file_id=%s (celery attempt %d/%d)",
        audio_file_id, self.request.retries + 1, self.max_retries + 1,
    )
    run_pipeline(UUID(audio_file_id))
