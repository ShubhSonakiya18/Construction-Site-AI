"""
tests/test_worker_matching.py — app/services/worker_matching.py.

Sprint 15, Deliverable 2 (ADR-061): matches LogSafetyIncident.worker_involved's
free text against real Worker records for OSHA reporting, exact-name-only
(no fuzzy matching -- the result can end up on a government compliance
form). Uses a real in-memory-DB WorkerRepository, matching
tests/test_db_repositories.py's own fixture pattern, since
match_worker_by_name() is session-bound (unlike schedule_service.py/
cost_service.py's pure-function modules).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.base import Base
from database.models.company import Company
from database.models.worker import Worker
from database.repositories.worker import WorkerRepository
from app.services.worker_matching import match_worker_by_name


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def make_company(session, name="Test Co"):
    company = Company(id=uuid.uuid4(), name=name, slug=name.lower().replace(" ", "-"))
    session.add(company)
    session.flush()
    return company


def make_worker(session, company, first_name, last_name, is_active=True):
    worker = Worker(
        id=uuid.uuid4(), company_id=company.id,
        first_name=first_name, last_name=last_name, is_active=is_active,
    )
    session.add(worker)
    session.flush()
    return worker


class TestMatchWorkerByName:
    def test_exact_full_name_match(self, session):
        company = make_company(session)
        worker = make_worker(session, company, "James", "Thompson")
        session.commit()

        result = match_worker_by_name(
            WorkerRepository(session), company_id=company.id, name="James Thompson",
        )
        assert result.status == "matched"
        assert result.worker_id == worker.id

    def test_case_insensitive_match(self, session):
        company = make_company(session)
        worker = make_worker(session, company, "James", "Thompson")
        session.commit()

        result = match_worker_by_name(
            WorkerRepository(session), company_id=company.id, name="james thompson",
        )
        assert result.status == "matched"
        assert result.worker_id == worker.id

    def test_no_match_for_unknown_name(self, session):
        company = make_company(session)
        make_worker(session, company, "James", "Thompson")
        session.commit()

        result = match_worker_by_name(
            WorkerRepository(session), company_id=company.id, name="Nobody Special",
        )
        assert result.status == "no_match"
        assert result.worker_id is None

    def test_needs_review_when_two_active_workers_share_a_name(self, session):
        """A real possibility with common names -- must not silently pick
        one, since the result can end up on an OSHA compliance document."""
        company = make_company(session)
        make_worker(session, company, "James", "Thompson")
        make_worker(session, company, "James", "Thompson")
        session.commit()

        result = match_worker_by_name(
            WorkerRepository(session), company_id=company.id, name="James Thompson",
        )
        assert result.status == "needs_review"
        assert result.worker_id is None

    def test_needs_review_for_a_partial_name_not_matching_full_name(self, session):
        """"Miguel" alone matches a first-name substring but not any
        worker's exact full name -- ambiguous, not a confident match."""
        company = make_company(session)
        make_worker(session, company, "Miguel", "Fernandez")
        session.commit()

        result = match_worker_by_name(
            WorkerRepository(session), company_id=company.id, name="Miguel",
        )
        assert result.status == "needs_review"
        assert result.worker_id is None

    def test_none_name_is_no_match(self, session):
        company = make_company(session)
        result = match_worker_by_name(
            WorkerRepository(session), company_id=company.id, name=None,
        )
        assert result.status == "no_match"

    def test_blank_name_is_no_match(self, session):
        company = make_company(session)
        result = match_worker_by_name(
            WorkerRepository(session), company_id=company.id, name="   ",
        )
        assert result.status == "no_match"

    def test_inactive_worker_is_not_matched(self, session):
        """find_by_name() already filters to active workers -- confirms
        that exclusion carries through to a real match attempt."""
        company = make_company(session)
        make_worker(session, company, "James", "Thompson", is_active=False)
        session.commit()

        result = match_worker_by_name(
            WorkerRepository(session), company_id=company.id, name="James Thompson",
        )
        assert result.status == "no_match"

    def test_does_not_match_a_worker_from_a_different_company(self, session):
        company_a = make_company(session, "Company A")
        company_b = make_company(session, "Company B")
        make_worker(session, company_b, "James", "Thompson")
        session.commit()

        result = match_worker_by_name(
            WorkerRepository(session), company_id=company_a.id, name="James Thompson",
        )
        assert result.status == "no_match"
