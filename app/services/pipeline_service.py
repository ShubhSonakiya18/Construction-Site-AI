"""
app/services/pipeline_service.py — Orchestrates the full voice-to-documents pipeline.

Chains four independent Sprint 1-6 subsystems for one AudioFile:
    1. speech.SpeechProcessingPipeline.process()      audio file -> transcript
    2. extraction.ExtractionPipeline.extract()         transcript -> ConstructionDailyLog dict
    3. DailyLogRepository.create_from_extraction_result()  dict -> daily_logs row + children
    4. generation.AIServiceManager.generate_all()      dict -> 4 documents
       GenerationRepository.create_from_service_output()   documents -> generation_outputs rows

Runs as a FastAPI BackgroundTask (see app/api/v1/audio.py) — started after
the upload response has already been sent to the client. Progress is
tracked entirely through AudioFile.processing_status, polled via
GET /audio/{id}/status (app/api/v1/audio.py).

Why this function takes only an audio_file_id (a UUID), not any live
object:
    A BackgroundTask runs after the request/response cycle completes — the
    original Session, Request, and any ORM objects loaded during the
    request are gone or detached. This function opens its own fresh
    Session via get_db-equivalent (get_engine + get_session), exactly like
    a Sprint 1-6 CLI script would. This is also what makes the Celery
    extension point trivial: a Celery task signature is `(audio_file_id: UUID)`
    too — swapping `BackgroundTasks.add_task(run_pipeline, id)` for
    `run_pipeline.delay(id)` (Sprint 8) requires no change inside this
    function, only at the call site in audio.py.

Error handling:
    Every Sprint 1-6 pipeline stage already returns a structured result
    with success=False + errors instead of raising for expected failure
    modes (SpeechProcessingResult, ExtractionResult, GenerationResult).
    This function checks .success at each stage and marks
    AudioFile.processing_status = "failed" with the error captured, rather
    than letting an exception propagate out of a background task (which
    FastAPI would only log, with no way for the client to ever see it —
    the client only has the polling endpoint).
"""
from __future__ import annotations

import logging
from uuid import UUID

from database.config import DatabaseConfig
from database.models.audio import SpeechTranscript
from database.models.company import User
from database.repositories.audio import AudioRepository, SpeechTranscriptRepository
from database.repositories.daily_log import DailyLogRepository
from database.repositories.generation import GenerationRepository
from database.session import get_engine, get_session

logger = logging.getLogger("app.pipeline")


def run_pipeline(audio_file_id: UUID) -> None:
    """Run transcribe -> extract -> persist -> generate -> persist for one AudioFile.

    Never raises — every failure is captured onto AudioFile.processing_status
    so GET /audio/{id}/status can report it to the client.
    """
    engine = get_engine(DatabaseConfig.from_env())

    with get_session(engine) as session:
        audio_repo = AudioRepository(session)
        audio_file = audio_repo.get_by_id(audio_file_id)
        if audio_file is None:
            logger.error("run_pipeline: AudioFile %s not found — aborting.", audio_file_id)
            return
        file_path = audio_file.file_path
        project_id = audio_file.project_id
        uploaded_by_id = audio_file.uploaded_by_id

        # DailyLog.foreman_id is a real FK to workers.id, NOT users.id.
        # uploaded_by_id (AudioFile.uploaded_by_id) is a users.id — the
        # logged-in account that uploaded the recording, which may or may
        # not correspond to a Worker row. User.worker_id is the (nullable)
        # link between the two. Passing uploaded_by_id directly as
        # foreman_id violates fk_daily_logs_foreman_id_workers whenever the
        # uploading user has no linked worker record (e.g. the Sprint 7
        # dev-admin account, which is an owner/admin login, not a foreman
        # with a workers.id). foreman_id is nullable on DailyLog, so the
        # correct behavior is: resolve it if possible, leave it unset
        # otherwise — never guess.
        foreman_id = None
        if uploaded_by_id is not None:
            uploading_user = session.get(User, uploaded_by_id)
            if uploading_user is not None and uploading_user.worker_id is not None:
                foreman_id = uploading_user.worker_id

        audio_repo.mark_status(audio_file, "transcribing")

    # ── Stage 1: Speech-to-text (Sprint 3) ────────────────────────────────────
    try:
        from speech.config import SpeechProcessingConfig
        from speech.pipeline import SpeechProcessingPipeline

        speech_pipeline = SpeechProcessingPipeline(config=SpeechProcessingConfig.from_env())
        speech_result = speech_pipeline.process(
            str(file_path), project_id=str(project_id) if project_id else None,
            audio_id=str(audio_file_id),
        )
    except Exception:
        logger.exception("run_pipeline: transcription raised for %s", audio_file_id)
        _mark_failed(engine, audio_file_id, "Transcription failed unexpectedly.")
        return

    if not speech_result.success or not speech_result.plain_text():
        _mark_failed(
            engine, audio_file_id,
            "; ".join(speech_result.errors) or "Transcription produced no text.",
        )
        return

    with get_session(engine) as session:
        audio_repo = AudioRepository(session)
        audio_file = audio_repo.get_by_id(audio_file_id)
        audio_repo.mark_status(audio_file, "extracting")

        SpeechTranscriptRepository(session).create(
            SpeechTranscript(
                audio_file_id=audio_file_id,
                raw_text=speech_result.plain_text(),
                language_code=speech_result.language() or "en",
                duration_seconds=speech_result.duration_seconds(),
                avg_confidence=speech_result.confidence(),
            )
        )

    # ── Stage 2: AI extraction (Sprint 4) ─────────────────────────────────────
    try:
        from extraction.config import ExtractionConfig
        from extraction.pipeline import ExtractionPipeline

        extraction_pipeline = ExtractionPipeline(config=ExtractionConfig.from_env())
        extraction_result = extraction_pipeline.extract(
            speech_result.plain_text(),
            audio_id=str(audio_file_id),
            project_id=str(project_id) if project_id else None,
        )
    except Exception:
        logger.exception("run_pipeline: extraction raised for %s", audio_file_id)
        _mark_failed(engine, audio_file_id, "AI extraction failed unexpectedly.")
        return

    if not extraction_result.success or not extraction_result.extracted_log:
        _mark_failed(
            engine, audio_file_id,
            "; ".join(extraction_result.errors) or "Extraction produced no data.",
        )
        return

    log_dict = extraction_result.extracted_log
    log_dict.pop("log_id", None)  # LLM-provided log_id is not a valid UUID — let the repo mint one

    # ── Stage 3: Persist DailyLog (Sprint 6) ──────────────────────────────────
    #
    # Duplicate check BEFORE attempting the insert. daily_logs has a
    # UNIQUE(project_id, log_date) constraint (one log per project per day) —
    # a second recording for the same project on the same calendar day is a
    # realistic business scenario (a foreman re-records after a mistake, or
    # two people log the same project the same day), not a server error.
    # Checking first means it surfaces to the client as a specific, actionable
    # "a log already exists" message instead of a raw IntegrityError caught by
    # the generic except-Exception block below and reported as an opaque
    # "Failed to save extracted daily log."
    #
    # This is a pre-check, not a lock — a real race between two concurrent
    # uploads for the same project+day is still possible and would still hit
    # the except-Exception fallback below. That is acceptable for Sprint 7:
    # the common case (sequential uploads) gets a clear message; the rare
    # concurrent case still fails safely, just with a less specific one.
    # AudioFile.project_id is nullable — audio may be uploaded before project
    # assignment (database/models/audio.py). But daily_logs.project_id is
    # NOT NULL: a DailyLog cannot exist without a project. Without this
    # check, an audio file uploaded with no project_id would reach the
    # insert below and fail with a raw psycopg2.errors.NotNullViolation,
    # caught only by the generic except-Exception fallback and reported to
    # the client as an opaque "Failed to save extracted daily log." — found
    # during Sprint 7/8 manual verification. Failing here instead gives a
    # specific, actionable message and avoids running Stage 2 extraction's
    # output through a doomed insert attempt.
    if project_id is None:
        message = (
            "This recording has no project assigned, so the extracted daily "
            "log cannot be saved. Re-upload with a project_id, or assign one "
            "to this recording before processing."
        )
        _mark_failed(engine, audio_file_id, message)
        return

    with get_session(engine) as session:
        log_date = DailyLogRepository.resolve_log_date(log_dict)
        existing = DailyLogRepository(session).get_by_project_date(project_id, log_date)
        if existing is not None:
            message = (
                f"A daily log already exists for this project on {log_date.isoformat()} "
                f"(daily_log_id={existing.id}). Upload rejected to avoid overwriting it."
            )
            logger.info(
                "run_pipeline: %s duplicate for project=%s date=%s -> existing log %s",
                audio_file_id, project_id, log_date, existing.id,
            )
            _mark_failed(engine, audio_file_id, message)
            return

    try:
        with get_session(engine) as session:
            audio_repo = AudioRepository(session)
            audio_file = audio_repo.get_by_id(audio_file_id)
            audio_repo.mark_status(audio_file, "generating")

            daily_log = DailyLogRepository(session).create_from_extraction_result(
                log_dict, project_id,
                audio_file_id=audio_file_id,
                foreman_id=foreman_id,  # workers.id or None — see resolution note above
                created_by_id=uploaded_by_id,  # AuditUserMixin, no FK constraint — users.id is correct
            )
            daily_log_id = daily_log.id
    except Exception:
        logger.exception("run_pipeline: persisting DailyLog raised for %s", audio_file_id)
        _mark_failed(engine, audio_file_id, "Failed to save extracted daily log.")
        return

    # ── Stage 4: AI generation (Sprint 5) ─────────────────────────────────────
    try:
        from generation.config import GenerationConfig
        from generation.manager import AIServiceManager

        manager = AIServiceManager(config=GenerationConfig.from_env())
        gen_result = manager.generate_all(log_dict)
    except Exception:
        logger.exception("run_pipeline: generation raised for %s", audio_file_id)
        _mark_complete(engine, audio_file_id, daily_log_id)  # log itself is safely saved
        return

    # ── Stage 5: Persist generation outputs (Sprint 6) ────────────────────────
    outputs = [
        gen_result.daily_report, gen_result.customer_update,
        gen_result.safety_talk, gen_result.material_reminder,
    ]
    with get_session(engine) as session:
        gen_repo = GenerationRepository(session)
        for output in outputs:
            if output and output.content:
                gen_repo.create_from_service_output(daily_log_id, output)

    _mark_complete(engine, audio_file_id, daily_log_id)


def _mark_failed(engine, audio_file_id: UUID, error_message: str) -> None:
    with get_session(engine) as session:
        audio_repo = AudioRepository(session)
        audio_file = audio_repo.get_by_id(audio_file_id)
        if audio_file is not None:
            audio_file.validation_errors = [error_message]
            audio_repo.mark_status(audio_file, "failed")
    logger.warning("run_pipeline: %s failed — %s", audio_file_id, error_message)


def _mark_complete(engine, audio_file_id: UUID, daily_log_id: UUID) -> None:
    with get_session(engine) as session:
        audio_repo = AudioRepository(session)
        audio_file = audio_repo.get_by_id(audio_file_id)
        if audio_file is not None:
            audio_repo.mark_status(audio_file, "complete")
    logger.info("run_pipeline: %s complete -> daily_log %s", audio_file_id, daily_log_id)
