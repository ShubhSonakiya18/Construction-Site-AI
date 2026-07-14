"""
tests/test_pipeline_service.py — Tests for app/services/pipeline_service.py.

Covers two bugs found and fixed during live end-to-end verification of the
real audio-upload pipeline against a real PostgreSQL database and real
Groq/Whisper calls (not reproducible by SQLite-in-memory unit tests alone —
this file locks in the fix with unit-level coverage so it cannot regress
silently, but the live verification is what originally caught it):

1. Duplicate daily_log for the same (project_id, log_date) crashed with a
   raw psycopg2.errors.UniqueViolation surfaced as an opaque "Failed to
   save extracted daily log." — fixed by pre-checking with
   DailyLogRepository.get_by_project_date() before attempting the insert.

2. DailyLog.foreman_id (a real FK to workers.id) was populated directly
   from AudioFile.uploaded_by_id (a users.id) — violated
   fk_daily_logs_foreman_id_workers whenever the uploading user had no
   linked Worker row (e.g. every Sprint 7 dev-admin login, which is an
   owner/admin account, not a foreman). Fixed by resolving foreman_id via
   User.worker_id, leaving it None when unresolvable (it's nullable).

Sprint 3/4/5 pipeline stages (Whisper, Groq extraction, Groq generation)
are monkeypatched — this file tests the Sprint 6/7 persistence-and-linking
logic in pipeline_service.py, not the AI calls themselves (those are
covered by tests/test_speech_*.py, tests/test_extraction_*.py,
tests/test_generation_*.py and this session's live manual verification).
"""
from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from database.base import Base
from database.models.audio import AudioFile
from database.models.company import Company, User
from database.models.daily_log import DailyLog
from database.models.project import Project
from database.models.worker import Worker
from database.repositories.audio import AudioRepository
from database.repositories.daily_log import DailyLogRepository
from database.session import get_engine, get_session, reset_engine


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture(autouse=True)
def _wire_default_engine(engine, monkeypatch):
    """pipeline_service.run_pipeline() calls get_engine(DatabaseConfig.from_env())
    internally — point the module-level singleton at our in-memory engine for
    the duration of each test."""
    reset_engine()
    import database.session as session_module
    monkeypatch.setattr(session_module, "_engine", engine)
    yield
    reset_engine()


@pytest.fixture
def company(engine):
    with Session(engine) as s:
        c = Company(name="Pipeline Test Co", slug="pipeline-test-co")
        s.add(c)
        s.commit()
        s.refresh(c)
        return c


@pytest.fixture
def project(engine, company):
    with Session(engine) as s:
        p = Project(company_id=company.id, name="Pipeline Test Project", status="active")
        s.add(p)
        s.commit()
        s.refresh(p)
        return p


def _make_extraction_result(log_date: str | None = "2026-06-01"):
    """A minimal, successful ExtractionResult-shaped object — enough fields
    for create_from_extraction_result() to run without error."""
    return SimpleNamespace(
        success=True,
        extracted_log={
            "log_date": log_date,
            "current_stage": "framing",
            "workforce": {"total_workers_present": 5},
        },
        errors=[],
    )


def _patch_pipeline_stages(monkeypatch, extraction_result):
    """Stub out Whisper/Groq so only the persistence logic under test runs."""
    import app.services.pipeline_service as svc

    fake_speech_result = SimpleNamespace(
        success=True,
        errors=[],
        transcript=SimpleNamespace(),
        plain_text=lambda: "eight workers on site today",
        language=lambda: "en",
        duration_seconds=lambda: 12.0,
        confidence=lambda: 0.9,
    )

    class FakeSpeechPipeline:
        def __init__(self, config=None):
            pass

        def process(self, *a, **k):
            return fake_speech_result

    class FakeExtractionPipeline:
        def __init__(self, config=None):
            pass

        def extract(self, *a, **k):
            return extraction_result

    fake_gen_result = SimpleNamespace(
        daily_report=SimpleNamespace(content="", service_type=SimpleNamespace(value="daily_report")),
        customer_update=SimpleNamespace(content="", service_type=SimpleNamespace(value="customer_update")),
        safety_talk=SimpleNamespace(content="", service_type=SimpleNamespace(value="safety_talk")),
        material_reminder=SimpleNamespace(content="", service_type=SimpleNamespace(value="material_reminder")),
    )

    class FakeAIServiceManager:
        def __init__(self, config=None):
            pass

        def generate_all(self, log_dict):
            return fake_gen_result

    monkeypatch.setattr("speech.pipeline.SpeechProcessingPipeline", FakeSpeechPipeline)
    monkeypatch.setattr("extraction.pipeline.ExtractionPipeline", FakeExtractionPipeline)
    monkeypatch.setattr("generation.manager.AIServiceManager", FakeAIServiceManager)


class TestDuplicateLogDetection:
    def test_second_upload_same_project_same_date_marks_failed_not_crash(
        self, engine, project, monkeypatch
    ):
        """Reproduces the exact bug: a daily_log already exists for
        (project_id, log_date) — the pipeline must detect this BEFORE
        attempting the insert and mark the AudioFile 'failed' with a
        specific, actionable message, never raise an unhandled IntegrityError."""
        from app.services.pipeline_service import run_pipeline

        with Session(engine) as s:
            existing = DailyLog(
                project_id=project.id,
                log_date=date(2026, 6, 1),
                current_stage="framing",
                total_workers_present=4,
            )
            s.add(existing)
            s.commit()
            existing_id = existing.id

            audio = AudioFile(
                project_id=project.id,
                original_filename="second.wav",
                file_path="/fake/second.wav",
                processing_status="pending",
            )
            s.add(audio)
            s.commit()
            audio_id = audio.id

        _patch_pipeline_stages(monkeypatch, _make_extraction_result(log_date="2026-06-01"))

        run_pipeline(audio_id)

        with Session(engine) as s:
            audio_repo = AudioRepository(s)
            audio_after = audio_repo.get_by_id(audio_id)
            assert audio_after.processing_status == "failed"
            assert audio_after.validation_errors is not None
            message = audio_after.validation_errors[0]
            assert "already exists" in message
            assert str(existing_id) in message
            assert "2026-06-01" in message

    def test_different_date_same_project_succeeds(self, engine, project, monkeypatch):
        """Sanity check the pre-check does not false-positive: a different
        log_date for the same project must succeed normally."""
        from app.services.pipeline_service import run_pipeline

        with Session(engine) as s:
            existing = DailyLog(
                project_id=project.id,
                log_date=date(2026, 6, 1),
                current_stage="framing",
                total_workers_present=4,
            )
            s.add(existing)
            s.commit()

            audio = AudioFile(
                project_id=project.id,
                original_filename="different_day.wav",
                file_path="/fake/different_day.wav",
                processing_status="pending",
            )
            s.add(audio)
            s.commit()
            audio_id = audio.id

        _patch_pipeline_stages(monkeypatch, _make_extraction_result(log_date="2026-06-02"))

        run_pipeline(audio_id)

        with Session(engine) as s:
            audio_after = AudioRepository(s).get_by_id(audio_id)
            assert audio_after.processing_status == "complete"

    def test_different_project_same_date_succeeds(self, engine, company, project, monkeypatch):
        """The uniqueness constraint is per-project — a second project on
        the same date must not be blocked by the first project's log."""
        from app.services.pipeline_service import run_pipeline

        with Session(engine) as s:
            s.add(DailyLog(
                project_id=project.id, log_date=date(2026, 6, 1),
                current_stage="framing", total_workers_present=4,
            ))
            other_project = Project(company_id=company.id, name="Other Project", status="active")
            s.add(other_project)
            s.commit()
            other_project_id = other_project.id

            audio = AudioFile(
                project_id=other_project_id,
                original_filename="other_project.wav",
                file_path="/fake/other_project.wav",
                processing_status="pending",
            )
            s.add(audio)
            s.commit()
            audio_id = audio.id

        _patch_pipeline_stages(monkeypatch, _make_extraction_result(log_date="2026-06-01"))

        run_pipeline(audio_id)

        with Session(engine) as s:
            audio_after = AudioRepository(s).get_by_id(audio_id)
            assert audio_after.processing_status == "complete"


class TestNoProjectIdHandling:
    def test_upload_with_no_project_id_marks_failed_not_crash(self, engine, monkeypatch):
        """Reproduces a real bug found during Sprint 7/8 manual verification:
        AudioFile.project_id is nullable (database/models/audio.py — "audio
        may be uploaded before project assignment"), but daily_logs.project_id
        is NOT NULL. Before this fix, an audio file with no project_id
        reached the DailyLog insert and crashed with a raw
        psycopg2.errors.NotNullViolation, caught only by the generic
        except-Exception fallback and reported as an opaque "Failed to save
        extracted daily log." The pipeline must instead detect this before
        attempting the insert and mark the AudioFile 'failed' with a
        specific, actionable message telling the client to assign a project."""
        from app.services.pipeline_service import run_pipeline

        with Session(engine) as s:
            audio = AudioFile(
                project_id=None,
                original_filename="no_project.wav",
                file_path="/fake/no_project.wav",
                processing_status="pending",
            )
            s.add(audio)
            s.commit()
            audio_id = audio.id

        _patch_pipeline_stages(monkeypatch, _make_extraction_result(log_date="2026-06-01"))

        run_pipeline(audio_id)

        with Session(engine) as s:
            audio_after = AudioRepository(s).get_by_id(audio_id)
            assert audio_after.processing_status == "failed"
            assert audio_after.validation_errors is not None
            message = audio_after.validation_errors[0]
            assert "no project assigned" in message
            assert "project_id" in message


class TestForemanIdResolution:
    def test_uploader_with_no_linked_worker_leaves_foreman_id_null(
        self, engine, company, project, monkeypatch
    ):
        """Reproduces the exact bug: an uploading User with no
        User.worker_id link (e.g. the dev-admin account) must not have
        their users.id written into DailyLog.foreman_id (a workers.id FK)
        — foreman_id must be left None instead."""
        from app.services.pipeline_service import run_pipeline

        with Session(engine) as s:
            uploader = User(
                company_id=company.id, email="admin-no-worker@example.com",
                first_name="Admin", last_name="NoWorker", role="owner",
                worker_id=None,
            )
            s.add(uploader)
            s.commit()
            uploader_id = uploader.id

            audio = AudioFile(
                project_id=project.id, uploaded_by_id=uploader_id,
                original_filename="admin_upload.wav", file_path="/fake/admin_upload.wav",
                processing_status="pending",
            )
            s.add(audio)
            s.commit()
            audio_id = audio.id

        _patch_pipeline_stages(monkeypatch, _make_extraction_result(log_date="2026-06-05"))

        run_pipeline(audio_id)

        with Session(engine) as s:
            audio_after = AudioRepository(s).get_by_id(audio_id)
            assert audio_after.processing_status == "complete", audio_after.validation_errors
            created_log = DailyLogRepository(s).get_by_project_date(project.id, date(2026, 6, 5))
            assert created_log is not None
            assert created_log.foreman_id is None
            # created_by_id has no FK constraint (ADR-026) — it correctly
            # keeps the raw users.id for audit purposes.
            assert created_log.created_by_id == uploader_id

    def test_uploader_with_linked_worker_resolves_foreman_id(
        self, engine, company, project, monkeypatch
    ):
        """When the uploading User DOES have a linked Worker (User.worker_id
        set), foreman_id should resolve to that worker's id, not the
        user's id."""
        from app.services.pipeline_service import run_pipeline

        with Session(engine) as s:
            worker = Worker(company_id=company.id, first_name="David", last_name="Rivera")
            s.add(worker)
            s.commit()
            worker_id = worker.id

            uploader = User(
                company_id=company.id, email="foreman@example.com",
                first_name="David", last_name="Rivera", role="foreman",
                worker_id=worker_id,
            )
            s.add(uploader)
            s.commit()
            uploader_id = uploader.id

            audio = AudioFile(
                project_id=project.id, uploaded_by_id=uploader_id,
                original_filename="foreman_upload.wav", file_path="/fake/foreman_upload.wav",
                processing_status="pending",
            )
            s.add(audio)
            s.commit()
            audio_id = audio.id

        _patch_pipeline_stages(monkeypatch, _make_extraction_result(log_date="2026-06-06"))

        run_pipeline(audio_id)

        with Session(engine) as s:
            audio_after = AudioRepository(s).get_by_id(audio_id)
            assert audio_after.processing_status == "complete", audio_after.validation_errors
            created_log = DailyLogRepository(s).get_by_project_date(project.id, date(2026, 6, 6))
            assert created_log is not None
            assert created_log.foreman_id == worker_id

    def test_no_uploader_at_all_leaves_foreman_id_null(self, engine, project, monkeypatch):
        """AudioFile.uploaded_by_id is nullable — no uploader on record must
        not crash the foreman_id resolution lookup."""
        from app.services.pipeline_service import run_pipeline

        with Session(engine) as s:
            audio = AudioFile(
                project_id=project.id, uploaded_by_id=None,
                original_filename="anon_upload.wav", file_path="/fake/anon_upload.wav",
                processing_status="pending",
            )
            s.add(audio)
            s.commit()
            audio_id = audio.id

        _patch_pipeline_stages(monkeypatch, _make_extraction_result(log_date="2026-06-07"))

        run_pipeline(audio_id)

        with Session(engine) as s:
            audio_after = AudioRepository(s).get_by_id(audio_id)
            assert audio_after.processing_status == "complete", audio_after.validation_errors
            created_log = DailyLogRepository(s).get_by_project_date(project.id, date(2026, 6, 7))
            assert created_log.foreman_id is None
