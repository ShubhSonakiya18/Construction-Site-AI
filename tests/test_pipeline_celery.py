"""
tests/test_pipeline_celery.py — Sprint 9: Celery task queue integration tests.

Uses celery_app.conf.task_always_eager=True so run_pipeline_task.delay()
executes synchronously in-process instead of round-tripping through a real
Redis broker — no live Redis required for this test file or CI, per
docs/NEXT_SPRINT.md Deliverable 5's stated approach. A live Redis
connection is exercised only via manual verification (see
docs/BACKEND_STARTUP.md), matching how tests/test_extraction_pipeline.py's
one real-Groq test is the live check for that integration, not the whole
suite's baseline.

Reuses fixtures/helpers from tests/test_pipeline_service.py (the in-memory
engine wiring and the Whisper/Groq/generation stand-ins) rather than
duplicating them — this file tests the QUEUING layer Sprint 9 added
(does .delay() actually invoke run_pipeline() with the right argument,
does eager mode surface exceptions the way retry expects), not the
persistence logic that file already covers.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from database.models.audio import AudioFile
from tests.test_pipeline_service import (  # noqa: F401 — reused as fixtures
    _make_extraction_result,
    _patch_pipeline_stages,
    _wire_default_engine,
    company,
    engine,
    project,
)


@pytest.fixture(autouse=True)
def _celery_eager():
    """Force in-process, synchronous task execution for this file only —
    restored after each test so other test files are unaffected."""
    from celery_app import celery_app

    original_eager = celery_app.conf.task_always_eager
    original_propagates = celery_app.conf.task_eager_propagates
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = original_eager
    celery_app.conf.task_eager_propagates = original_propagates


def _make_audio_file(engine, project) -> str:
    from sqlalchemy.orm import Session

    with Session(engine) as s:
        audio = AudioFile(
            project_id=project.id,
            original_filename="site_note.wav",
            stored_filename="stored.wav",
            file_path="/fake/stored.wav",
            file_size_bytes=1024,
            format="wav",
            processing_status="pending",
        )
        s.add(audio)
        s.commit()
        s.refresh(audio)
        return str(audio.id)


class TestRunPipelineTaskEager:
    def test_delay_invokes_run_pipeline_and_marks_complete(
        self, engine, project, monkeypatch
    ):
        """The Celery integration point itself: .delay(str(id)) must reach
        the real run_pipeline() with a UUID it can use — Celery's JSON
        serializer only carries the id as str, and run_pipeline_task is
        responsible for converting it back (see app/tasks/pipeline_tasks.py)."""
        _patch_pipeline_stages(monkeypatch, _make_extraction_result())
        audio_id = _make_audio_file(engine, project)

        from app.tasks.pipeline_tasks import run_pipeline_task

        run_pipeline_task.delay(audio_id)

        import uuid

        from sqlalchemy.orm import Session

        with Session(engine) as s:
            audio = s.get(AudioFile, uuid.UUID(audio_id))
            assert audio.processing_status == "complete"

    def test_delay_accepts_string_id_not_just_uuid_object(
        self, engine, project, monkeypatch
    ):
        """Guards the exact bug class this task wrapper exists to prevent:
        passing a UUID object (as the pre-Sprint-9 direct call did) instead
        of a str would silently fail Celery's real JSON serialization in
        production, even though it works by accident in eager mode. This
        test asserts the router's actual call shape — str(audio_file.id) —
        is what the task is built for."""
        _patch_pipeline_stages(monkeypatch, _make_extraction_result())
        audio_id = _make_audio_file(engine, project)
        assert isinstance(audio_id, str)

        from app.tasks.pipeline_tasks import run_pipeline_task

        # Round-trips through Celery's real JSON serializer even in eager
        # mode, unlike calling run_pipeline_task.run() directly — this is
        # what actually proves a UUID object would NOT have worked.
        result = run_pipeline_task.apply_async(args=[audio_id])
        assert result.successful()

    def test_nonexistent_audio_file_id_returns_without_raising(
        self, engine, project, monkeypatch
    ):
        """run_pipeline()'s own not-found guard (audio_file is None -> log
        + return) must still hold when invoked through the Celery wrapper —
        the task should not raise, retry, or crash for a missing row."""
        import uuid

        from app.tasks.pipeline_tasks import run_pipeline_task

        result = run_pipeline_task.apply_async(args=[str(uuid.uuid4())])
        assert result.successful()


class TestCeleryAppConfig:
    def test_broker_and_backend_use_different_redis_logical_dbs(self):
        """Settings.celery_broker_url and celery_result_backend must not
        collide with each other or with redis_rate_limit_url — see
        app/core/config.py's docstring on why (a debugging FLUSHDB against
        one must not silently wipe another's state)."""
        from app.core.config import Settings

        s = Settings(_env_file=None)
        broker_db = s.celery_broker_url.rsplit("/", 1)[-1]
        backend_db = s.celery_result_backend.rsplit("/", 1)[-1]
        rate_limit_db = s.redis_rate_limit_url.rsplit("/", 1)[-1]
        assert len({broker_db, backend_db, rate_limit_db}) == 3

    def test_task_time_limits_are_configured(self):
        from celery_app import celery_app

        assert celery_app.conf.task_time_limit == 900
        assert celery_app.conf.task_soft_time_limit == 840

    def test_pipeline_task_is_registered(self):
        from celery_app import celery_app

        assert "app.tasks.pipeline_tasks.run_pipeline_task" in celery_app.tasks
