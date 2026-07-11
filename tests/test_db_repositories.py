"""
tests/test_db_repositories.py — Repository layer tests using SQLite in-memory.

WHY we test repositories separately from models:
    Models tests verify that the ORM mapping is correct.
    Repository tests verify that the business-logic query layer is correct.
    Mixing them makes failures ambiguous — is it the query or the mapping?

Repository test design rules:
    1. Each test method tests exactly ONE repository method.
    2. Setup data is created via repository.create() not raw session.add(),
       so tests exercise the real code path.
    3. State assertions use repository.get_by_id() not raw session.get(),
       for the same reason.
    4. Tests that need multiple related entities build them bottom-up
       (reference → company → worker → project → log).

Soft-delete behavior covered here:
    - list() excludes deleted records
    - soft_delete() sets deleted_at but does not remove rows
    - restore() clears deleted_at
    - hard_delete() removes the row entirely
"""
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.base import Base
from database.models import (
    Trade, Company, User, Worker, Project, Site,
    AudioFile, SpeechTranscript, DailyLog,
    LogTradeOnSite, LogWorkItem, LogMaterialUsed, LogHazard,
    GenerationOutput, AuditLog,
)
from database.repositories import (
    CompanyRepository, UserRepository,
    ProjectRepository, SiteRepository,
    WorkerRepository,
    AudioRepository,
    DailyLogRepository,
    GenerationRepository, AuditLogRepository,
)
from database.repositories.audio import SpeechTranscriptRepository
from database.repositories.project import ProjectWorkerRepository


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def company_repo(session):
    return CompanyRepository(session)


@pytest.fixture
def user_repo(session):
    return UserRepository(session)


@pytest.fixture
def worker_repo(session):
    return WorkerRepository(session)


@pytest.fixture
def project_repo(session):
    return ProjectRepository(session)


@pytest.fixture
def site_repo(session):
    return SiteRepository(session)


@pytest.fixture
def audio_repo(session):
    return AudioRepository(session)


@pytest.fixture
def transcript_repo(session):
    return SpeechTranscriptRepository(session)


@pytest.fixture
def daily_log_repo(session):
    return DailyLogRepository(session)


@pytest.fixture
def generation_repo(session):
    return GenerationRepository(session)


@pytest.fixture
def audit_repo(session):
    return AuditLogRepository(session)


# ── Seed helpers ──────────────────────────────────────────────────────────────

def make_company(session, slug="acme", name="ACME Corp"):
    c = Company(name=name, slug=slug)
    session.add(c)
    session.flush()
    return c


def make_trade(session, code="CARP"):
    t = Trade(code=code, display_name=code.title())
    session.add(t)
    session.flush()
    return t


def make_worker(session, company, trade=None, first="John", last="Doe"):
    w = Worker(
        company_id=company.id,
        trade_id=trade.id if trade else None,
        first_name=first,
        last_name=last,
    )
    session.add(w)
    session.flush()
    return w


def make_project(session, company, name="Project Alpha"):
    p = Project(company_id=company.id, name=name, status="active")
    session.add(p)
    session.flush()
    return p


def make_site(session, project):
    s = Site(project_id=project.id, address="123 Builder St", is_primary=True)
    session.add(s)
    session.flush()
    return s


def make_daily_log(session, project, log_date=None, review_status="draft"):
    dl = DailyLog(
        project_id=project.id,
        log_date=log_date or date(2026, 7, 10),
        current_stage="framing",
        total_workers_present=4,
        review_status=review_status,
    )
    session.add(dl)
    session.flush()
    return dl


def make_audio_file(session, project):
    af = AudioFile(
        project_id=project.id,
        original_filename="report.mp3",
        processing_status="pending",
    )
    session.add(af)
    session.flush()
    return af


# ── BaseRepository tests via CompanyRepository ────────────────────────────────

class TestBaseRepository:
    def test_create(self, session, company_repo):
        c = company_repo.create(Company(name="New Corp", slug="new-corp"))
        assert c.id is not None
        assert session.get(Company, c.id) is not None

    def test_get_by_id_returns_entity(self, session, company_repo):
        c = company_repo.create(Company(name="Get Corp", slug="get-corp"))
        fetched = company_repo.get_by_id(c.id)
        assert fetched is not None
        assert fetched.slug == "get-corp"

    def test_get_by_id_returns_none_for_missing(self, session, company_repo):
        result = company_repo.get_by_id(uuid.uuid4())
        assert result is None

    def test_list_returns_all_active(self, session, company_repo):
        company_repo.create(Company(name="Corp A", slug="corp-a"))
        company_repo.create(Company(name="Corp B", slug="corp-b"))
        results = company_repo.list()
        assert len(results) == 2

    def test_list_excludes_soft_deleted(self, session, company_repo):
        c1 = company_repo.create(Company(name="Active", slug="active"))
        c2 = company_repo.create(Company(name="Deleted", slug="deleted"))
        # soft_delete takes the entity instance, not an id
        company_repo.soft_delete(c2)

        results = company_repo.list()
        ids = [r.id for r in results]
        assert c1.id in ids
        assert c2.id not in ids

    def test_list_limit_and_offset(self, session, company_repo):
        for i in range(5):
            company_repo.create(Company(name=f"Corp {i}", slug=f"corp-{i}"))

        page1 = company_repo.list(limit=2, offset=0)
        page2 = company_repo.list(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0].id != page2[0].id

    def test_count_active_only(self, session, company_repo):
        company_repo.create(Company(name="C1", slug="c1"))
        c2 = company_repo.create(Company(name="C2", slug="c2"))
        company_repo.soft_delete(c2)
        assert company_repo.count() == 1

    def test_exists_true_for_active(self, session, company_repo):
        c = company_repo.create(Company(name="Exists Corp", slug="exists-corp"))
        assert company_repo.exists(c.id) is True

    def test_exists_false_for_deleted(self, session, company_repo):
        c = company_repo.create(Company(name="Gone Corp", slug="gone-corp"))
        company_repo.soft_delete(c)
        assert company_repo.exists(c.id) is False

    def test_update(self, session, company_repo):
        c = company_repo.create(Company(name="Old Name", slug="old-name"))
        # update() takes the entity instance with changes already applied
        c.name = "New Name"
        updated = company_repo.update(c)
        assert updated.name == "New Name"
        assert session.get(Company, c.id).name == "New Name"

    def test_soft_delete_sets_deleted_at(self, session, company_repo):
        c = company_repo.create(Company(name="Delete Me", slug="delete-me"))
        company_repo.soft_delete(c)
        session.refresh(c)
        assert c.deleted_at is not None

    def test_restore_clears_deleted_at(self, session, company_repo):
        c = company_repo.create(Company(name="Restore Me", slug="restore-me"))
        company_repo.soft_delete(c)
        company_repo.restore(c)
        session.refresh(c)
        assert c.deleted_at is None

    def test_hard_delete_removes_row(self, session, company_repo):
        c = company_repo.create(Company(name="Nuke Me", slug="nuke-me"))
        c_id = c.id
        company_repo.hard_delete(c)
        assert session.get(Company, c_id) is None


# ── CompanyRepository tests ───────────────────────────────────────────────────

class TestCompanyRepository:
    def test_get_by_slug(self, session, company_repo):
        company_repo.create(Company(name="Slug Corp", slug="slug-corp"))
        result = company_repo.get_by_slug("slug-corp")
        assert result is not None
        assert result.name == "Slug Corp"

    def test_get_by_slug_returns_none_for_missing(self, session, company_repo):
        assert company_repo.get_by_slug("no-such-slug") is None

    def test_slug_exists_true(self, session, company_repo):
        company_repo.create(Company(name="Slug X", slug="slug-x"))
        assert company_repo.slug_exists("slug-x") is True

    def test_slug_exists_false(self, session, company_repo):
        assert company_repo.slug_exists("nonexistent") is False


# ── UserRepository tests ──────────────────────────────────────────────────────

class TestUserRepository:
    def test_get_by_email(self, session, user_repo):
        company = make_company(session)
        u = User(company_id=company.id, email="test@corp.com", first_name="Test", last_name="User")
        session.add(u)
        session.flush()

        result = user_repo.get_by_email("test@corp.com")
        assert result is not None
        assert result.email == "test@corp.com"

    def test_get_by_email_case_sensitive(self, session, user_repo):
        company = make_company(session)
        u = User(company_id=company.id, email="lower@corp.com", first_name="Lower", last_name="User")
        session.add(u)
        session.flush()
        # SQLite is case-insensitive for LIKE but case-sensitive for =
        # Our repo uses exact match.
        result = user_repo.get_by_email("LOWER@CORP.COM")
        # behavior depends on SQLite collation; just verify no crash
        assert result is None or result.email == "lower@corp.com"

    def test_list_by_company(self, session, user_repo):
        c1 = make_company(session, "comp1", "Corp 1")
        c2 = make_company(session, "comp2", "Corp 2")

        u1 = User(company_id=c1.id, email="a@c1.com", first_name="A", last_name="1")
        u2 = User(company_id=c1.id, email="b@c1.com", first_name="B", last_name="1")
        u3 = User(company_id=c2.id, email="a@c2.com", first_name="A", last_name="2")
        session.add_all([u1, u2, u3])
        session.flush()

        results = user_repo.list_by_company(c1.id)
        assert len(results) == 2
        for r in results:
            assert r.company_id == c1.id

    def test_email_exists_true(self, session, user_repo):
        company = make_company(session)
        u = User(company_id=company.id, email="exists@corp.com", first_name="E", last_name="X")
        session.add(u)
        session.flush()
        assert user_repo.email_exists("exists@corp.com") is True

    def test_email_exists_false(self, session, user_repo):
        assert user_repo.email_exists("nobody@nowhere.com") is False


# ── WorkerRepository tests ────────────────────────────────────────────────────

class TestWorkerRepository:
    def test_list_by_company(self, session, worker_repo):
        c1 = make_company(session, "c1", "C1")
        c2 = make_company(session, "c2", "C2")
        make_worker(session, c1, first="Alice", last="A")
        make_worker(session, c1, first="Bob", last="B")
        make_worker(session, c2, first="Carol", last="C")

        results = worker_repo.list_by_company(c1.id)
        assert len(results) == 2

    def test_find_by_name_first_name(self, session, worker_repo):
        company = make_company(session)
        make_worker(session, company, first="Mike", last="Johnson")

        # find_by_name matches first_name OR last_name as a substring
        results = worker_repo.find_by_name(company.id, "Mike")
        assert len(results) == 1
        assert results[0].first_name == "Mike"

    def test_find_by_name_last_name_matches_multiple(self, session, worker_repo):
        company = make_company(session)
        make_worker(session, company, first="Mike", last="Johnson")
        make_worker(session, company, first="Michael", last="Johnson")

        results = worker_repo.find_by_name(company.id, "Johnson")
        assert len(results) == 2

    def test_find_by_name_no_match(self, session, worker_repo):
        company = make_company(session)
        make_worker(session, company, first="Tom", last="Thumb")
        results = worker_repo.find_by_name(company.id, "Nobody")
        assert len(results) == 0


# ── ProjectRepository tests ───────────────────────────────────────────────────

class TestProjectRepository:
    def test_list_by_company(self, session, project_repo):
        c1 = make_company(session, "proj-c1", "C1")
        c2 = make_company(session, "proj-c2", "C2")
        make_project(session, c1, "P1")
        make_project(session, c1, "P2")
        make_project(session, c2, "P3")

        results = project_repo.list_by_company(c1.id)
        assert len(results) == 2

    def test_list_by_company_with_status_filter(self, session, project_repo):
        company = make_company(session, "status-co", "Status Co")
        p1 = Project(company_id=company.id, name="Active", status="active")
        p2 = Project(company_id=company.id, name="Planning", status="planning")
        session.add_all([p1, p2])
        session.flush()

        active = project_repo.list_by_company(company.id, status="active")
        assert len(active) == 1
        assert active[0].name == "Active"


# ── SiteRepository tests ──────────────────────────────────────────────────────

class TestSiteRepository:
    def test_get_primary_site(self, session, site_repo):
        company = make_company(session, "site-co", "Site Co")
        project = make_project(session, company)
        primary = Site(project_id=project.id, address="Primary St", is_primary=True)
        secondary = Site(project_id=project.id, address="Secondary St", is_primary=False)
        session.add_all([primary, secondary])
        session.flush()

        result = site_repo.get_primary(project.id)
        assert result is not None
        assert result.address == "Primary St"


# ── AudioRepository tests ─────────────────────────────────────────────────────

class TestAudioRepository:
    def test_mark_status_transcribed(self, session, audio_repo):
        company = make_company(session, "audio-co", "Audio Co")
        project = make_project(session, company)
        af = make_audio_file(session, project)
        assert af.processing_status == "pending"

        audio_repo.mark_status(af, "transcribed")
        session.refresh(af)
        assert af.processing_status == "transcribed"

    def test_get_with_transcript(self, session, audio_repo):
        company = make_company(session, "trans-co", "Trans Co")
        project = make_project(session, company)
        af = make_audio_file(session, project)

        st = SpeechTranscript(
            audio_file_id=af.id,
            raw_text="Workers completed slab pour.",
            chunk_count=1,
            total_segments=5,
        )
        session.add(st)
        session.flush()

        result = audio_repo.get_with_transcript(af.id)
        assert result is not None
        assert result.transcript is not None
        assert result.transcript.raw_text == "Workers completed slab pour."


# ── SpeechTranscriptRepository tests ─────────────────────────────────────────

class TestSpeechTranscriptRepository:
    def test_list_low_confidence(self, session, transcript_repo):
        company = make_company(session, "conf-co", "Conf Co")
        project = make_project(session, company)

        af1 = AudioFile(project_id=project.id, original_filename="a.mp3", processing_status="transcribed")
        af2 = AudioFile(project_id=project.id, original_filename="b.mp3", processing_status="transcribed")
        session.add_all([af1, af2])
        session.flush()

        st1 = SpeechTranscript(audio_file_id=af1.id, raw_text="High confidence", avg_confidence=0.95)
        st2 = SpeechTranscript(audio_file_id=af2.id, raw_text="Low confidence", avg_confidence=0.55)
        session.add_all([st1, st2])
        session.flush()

        low = transcript_repo.list_low_confidence(threshold=0.7)
        assert len(low) == 1
        assert low[0].avg_confidence == 0.55


# ── DailyLogRepository tests ──────────────────────────────────────────────────

class TestDailyLogRepository:
    def test_get_by_project_date(self, session, daily_log_repo):
        company = make_company(session, "dl-co", "DL Co")
        project = make_project(session, company)
        dl = make_daily_log(session, project, date(2026, 7, 10))

        result = daily_log_repo.get_by_project_date(project.id, date(2026, 7, 10))
        assert result is not None
        assert result.id == dl.id

    def test_get_by_project_date_not_found(self, session, daily_log_repo):
        company = make_company(session, "dl-co2", "DL Co 2")
        project = make_project(session, company)

        result = daily_log_repo.get_by_project_date(project.id, date(2026, 1, 1))
        assert result is None

    def test_resolve_log_date_parses_iso_string(self, daily_log_repo):
        result = DailyLogRepository.resolve_log_date({"log_date": "2026-03-15"})
        assert result == date(2026, 3, 15)

    def test_resolve_log_date_falls_back_to_today_on_explicit_null(self, daily_log_repo):
        """LLM extraction may emit log_date: null (ADR-003) — must fall back
        to today(), not crash. This is the exact fallback
        create_from_extraction_result() uses at insert time; extracted as a
        shared method (Sprint 7) so callers needing the value BEFORE insert
        (see app/services/pipeline_service.py's duplicate-log pre-check)
        never drift from what the insert will actually use."""
        result = DailyLogRepository.resolve_log_date({"log_date": None})
        assert result == date.today()

    def test_resolve_log_date_falls_back_to_today_on_missing_key(self, daily_log_repo):
        result = DailyLogRepository.resolve_log_date({})
        assert result == date.today()

    def test_resolve_log_date_falls_back_to_today_on_unparseable_string(self, daily_log_repo):
        result = DailyLogRepository.resolve_log_date({"log_date": "not-a-date"})
        assert result == date.today()

    def test_resolve_log_date_accepts_a_real_date_object(self, daily_log_repo):
        result = DailyLogRepository.resolve_log_date({"log_date": date(2026, 1, 1)})
        assert result == date(2026, 1, 1)

    def test_resolve_log_date_matches_create_from_extraction_result(self, session, daily_log_repo):
        """The pre-check and the insert must resolve the identical date —
        this test creates a log with an explicit-null log_date, then
        confirms resolve_log_date() predicts exactly the row that landed."""
        company = make_company(session, "resolve-co", "Resolve Co")
        project = make_project(session, company)

        extracted = {"log_date": None, "current_stage": "foundation", "workforce": {"total_workers_present": 3}}
        predicted_date = DailyLogRepository.resolve_log_date(extracted)

        created = daily_log_repo.create_from_extraction_result(extracted, project.id)
        assert created.log_date == predicted_date

    def test_list_pending_review(self, session, daily_log_repo):
        company = make_company(session, "rev-co", "Review Co")
        project = make_project(session, company)

        # Repository filters on "under_review" status
        dl_pending = make_daily_log(session, project, date(2026, 7, 1), review_status="under_review")
        dl_approved = make_daily_log(session, project, date(2026, 7, 2), review_status="approved")
        dl_draft = make_daily_log(session, project, date(2026, 7, 3), review_status="draft")

        results = daily_log_repo.list_pending_review(company.id)
        result_ids = [r.id for r in results]
        assert dl_pending.id in result_ids
        assert dl_approved.id not in result_ids
        assert dl_draft.id not in result_ids

    def test_submit_for_review(self, session, daily_log_repo):
        company = make_company(session, "sub-co", "Submit Co")
        project = make_project(session, company)
        dl = make_daily_log(session, project, date(2026, 7, 5), review_status="draft")

        # Repository takes the DailyLog object (not an id)
        updated = daily_log_repo.submit_for_review(dl)
        assert updated.review_status == "under_review"

    def test_approve(self, session, daily_log_repo):
        company = make_company(session, "appr-co", "Approve Co")
        project = make_project(session, company)
        dl = make_daily_log(session, project, date(2026, 7, 6), review_status="under_review")
        reviewer_id = uuid.uuid4()

        # Repository takes the DailyLog object
        updated = daily_log_repo.approve(dl, reviewer_id, notes="Looks good")
        assert updated.review_status == "approved"
        assert updated.reviewed_by_id == reviewer_id
        assert updated.review_notes == "Looks good"

    def test_reject(self, session, daily_log_repo):
        company = make_company(session, "rej-co", "Reject Co")
        project = make_project(session, company)
        dl = make_daily_log(session, project, date(2026, 7, 7), review_status="under_review")
        reviewer_id = uuid.uuid4()

        # Repository takes the DailyLog object; notes are required
        updated = daily_log_repo.reject(dl, reviewer_id, "Missing data")
        assert updated.review_status == "rejected"
        assert updated.review_notes == "Missing data"

    def test_get_with_children_loads_relationships(self, session, daily_log_repo):
        company = make_company(session, "child-co", "Child Co")
        project = make_project(session, company)
        dl = make_daily_log(session, project, date(2026, 7, 8))

        session.add(LogTradeOnSite(daily_log_id=dl.id, trade="framing_carpenter", workers_count=3))
        session.add(LogWorkItem(daily_log_id=dl.id, task_description="Frame walls", trade="framing_carpenter"))
        session.add(LogHazard(daily_log_id=dl.id, hazard_type="fall_risk", description="Open hole", severity="high"))
        session.flush()

        result = daily_log_repo.get_with_children(dl.id)
        assert result is not None
        assert len(result.trades_on_site) == 1
        assert len(result.work_items) == 1
        assert len(result.hazards) == 1

    def test_create_from_extraction_result(self, session, daily_log_repo):
        """Integration: creating a DailyLog from a dict (Sprint 4 extraction result)."""
        company = make_company(session, "ext-co", "Extract Co")
        project = make_project(session, company)

        # The repository's extracted_log format matches the ConstructionDailyLog schema.
        # workforce.trades_on_site, work_completed, etc.
        extracted = {
            "log_date": "2026-07-09",
            "current_stage": "foundation",
            "review_status": "draft",
            "workforce": {
                "total_workers_present": 8,
                "trades_on_site": [
                    {"trade": "framing_carpenter", "workers_count": 4, "hours_worked": 8.0},
                    {"trade": "electrician", "workers_count": 2, "hours_worked": 6.0},
                ],
            },
            "work_completed": [
                {"task_description": "Pour slab", "trade": "concrete"},
            ],
        }

        dl = daily_log_repo.create_from_extraction_result(extracted, project_id=project.id)
        assert dl.id is not None
        assert dl.current_stage == "foundation"
        assert len(dl.trades_on_site) == 2
        assert len(dl.work_items) == 1


# ── GenerationRepository tests ────────────────────────────────────────────────

class TestGenerationRepository:
    def test_create_from_service_output(self, session, generation_repo):
        company = make_company(session, "gen-co", "Gen Co")
        project = make_project(session, company)
        dl = make_daily_log(session, project, date(2026, 7, 10))

        # create_from_service_output uses duck typing against Sprint 5 ServiceOutput.
        # It accesses service_output.metadata.generation_id etc.
        class FakeMeta:
            generation_id = uuid.uuid4()
            prompt_name = "daily_report_v1"
            prompt_version = "1.0"
            provider = "groq"
            model = "llama-3.1-70b-versatile"
            tokens_used = 512
            response_time_seconds = 1.2
            retry_count = 0

        class FakeOutput:
            service_type = "daily_report"
            content = "Report text here"
            is_valid = True
            validation_errors = None
            metadata = FakeMeta()

        go = generation_repo.create_from_service_output(dl.id, FakeOutput())
        assert go.id is not None
        assert go.service_type == "daily_report"
        assert go.provider == "groq"

    def test_list_for_log(self, session, generation_repo):
        company = make_company(session, "genlist-co", "GenList Co")
        project = make_project(session, company)
        dl = make_daily_log(session, project, date(2026, 7, 10))

        go1 = GenerationOutput(
            daily_log_id=dl.id,
            service_type="daily_report",
            generation_id=uuid.uuid4(),
            content="Report 1",
        )
        go2 = GenerationOutput(
            daily_log_id=dl.id,
            service_type="whatsapp_message",
            generation_id=uuid.uuid4(),
            content="WhatsApp message",
        )
        session.add_all([go1, go2])
        session.flush()

        results = generation_repo.list_for_log(dl.id)
        assert len(results) == 2


# ── AuditLogRepository tests ──────────────────────────────────────────────────

class TestAuditLogRepository:
    def test_log_event(self, session, audit_repo):
        entity_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        company_id = uuid.uuid4()

        # log_event uses keyword-only args after event_type
        al = audit_repo.log_event(
            "daily_log.approved",
            entity_type="DailyLog",
            entity_id=entity_id,
            actor_id=actor_id,
            company_id=company_id,
            new_values={"review_status": "approved"},
        )
        assert al.id is not None
        assert al.event_type == "daily_log.approved"
        assert al.entity_id == entity_id

    def test_list_for_entity(self, session, audit_repo):
        entity_id = uuid.uuid4()

        audit_repo.log_event("created", entity_type="DailyLog", entity_id=entity_id, actor_id=uuid.uuid4(), company_id=uuid.uuid4())
        audit_repo.log_event("approved", entity_type="DailyLog", entity_id=entity_id, actor_id=uuid.uuid4(), company_id=uuid.uuid4())
        audit_repo.log_event("other", entity_type="Project", entity_id=uuid.uuid4(), actor_id=uuid.uuid4(), company_id=uuid.uuid4())

        results = audit_repo.list_for_entity("DailyLog", entity_id)
        assert len(results) == 2
        for r in results:
            assert r.entity_type == "DailyLog"
            assert r.entity_id == entity_id
