"""
celery_app.py — Celery application instance for the audio pipeline task queue.

Sprint 9. Replaces Sprint 7's FastAPI BackgroundTasks invocation of
app.services.pipeline_service.run_pipeline() — see app/api/v1/audio.py for
the call-site change. run_pipeline()'s function body is unchanged: it was
deliberately shaped in Sprint 7 (signature (audio_file_id: UUID) -> None, no
shared request-scoped state, opens its own DB session) specifically so this
migration is a decorator + a call-site change, not a rewrite. See
docs/BACKEND_ARCHITECTURE.md §10.

Root-level module (not under app/), matching this repo's existing
convention for standalone process entry points (extract.py, report.py,
transcribe.py, generate.py) — a Celery worker is started as its own OS
process (`celery -A celery_app worker`), not imported by the FastAPI app.

Why load_dotenv() here too:
    Same reasoning as app/main.py: a `celery -A celery_app worker` process
    is a fresh Python process that never goes through app/main.py, so
    DATABASE_URL / GROQ_API_KEY / CELERY_BROKER_URL etc. would otherwise
    only be visible if exported into the shell manually — the exact gotcha
    documented in docs/BACKEND_STARTUP.md for Alembic and dev_seed. Loading
    .env here means `celery -A celery_app worker` works the same way
    `uvicorn app.main:app` does, with no extra shell setup.

Why Redis for both broker and result backend:
    Sprint 9 introduces Redis as new infrastructure specifically for this
    task queue; using it for both roles avoids a second broker/backend
    technology (e.g. RabbitMQ) for a single-purpose task queue at this
    project's scale. app/core/config.py's celery_result_backend uses a
    different Redis logical DB (1) than the broker (0) and
    RedisRateLimiter's future DB (2), so a debugging FLUSHDB against one
    can't silently wipe another's state.
"""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from celery import Celery  # noqa: E402 — must follow load_dotenv()

from app.core.config import get_settings  # noqa: E402

_settings = get_settings()

celery_app = Celery(
    "construction_site_ai",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=["app.tasks.pipeline_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # A stuck/hung task (e.g. a Whisper model load that never returns)
    # should not silently occupy a worker forever — this matches the
    # spirit of extraction/generation's own retry+timeout discipline,
    # just at the task level instead of the LLM-call level.
    task_time_limit=900,  # hard kill after 15 minutes
    task_soft_time_limit=840,  # SoftTimeLimitExceeded raised 1 min earlier
    # Retry policy for transient failures (Groq rate limits, Whisper OOM),
    # per docs/NEXT_SPRINT.md Deliverable 1 — see app/tasks/pipeline_tasks.py
    # for where this is applied; task_acks_late+reject_on_worker_lost mean a
    # worker crash mid-task re-queues the task instead of losing it silently.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # audio processing tasks are long-running; don't hoard
    # Explicit per Celery 5.4's own deprecation warning: this flag's
    # meaning changes in Celery 6.0, so pin the current (retry-on-startup)
    # behavior now rather than silently inherit whatever 6.0 defaults to.
    broker_connection_retry_on_startup=True,
)
