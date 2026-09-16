"""
tests/test_api_osha_log.py — Sprint 15, Deliverable 3:
GET /projects/{id}/osha-300-log.

Same two-company tenant-isolation pattern every Sprint 10+ API test
file uses. Live-verified separately against the real database and real
Groq (docs/DECISIONS.md) -- these tests cover the endpoint's wiring
(permission gate, readiness filtering, response shape) with small
hand-built fixtures.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.core.security import create_access_token
from database.models.company import Company, User
from database.models.daily_log import DailyLog
from database.models.log_items import LogSafetyIncident
from database.models.project import Project
from database.models.worker import Worker
from database.seed.sample_data import COMPANY_ID, PROJECT_ID

pytest_plugins = ["tests.conftest_api"]

OSHA_URL = f"/api/v1/projects/{PROJECT_ID}/osha-300-log"


def _make_user_and_token(seeded_session, test_settings, *, role: str, email: str):
    user = User(
        company_id=COMPANY_ID, email=email, first_name="OSHA",
        last_name="Test", role=role, is_active=True,
    )
    seeded_session.add(user)
    seeded_session.flush()
    seeded_session.commit()

    token = create_access_token(
        subject=str(user.id),
        secret_key=test_settings.jwt_secret_key,
        extra_claims={"company_id": str(COMPANY_ID), "role": role, "email": email},
    )
    return user, token


class TestPermissionGate:
    def test_requires_authentication(self, api_client):
        response = api_client.get(f"{OSHA_URL}?year=2026")
        assert response.status_code == 401

    def test_client_role_is_forbidden(self, api_client, seeded_session, test_settings):
        """client holds DAILY_LOG_READ/PROJECT_READ but not
        DAILY_LOG_GENERATE -- this endpoint produces an official
        compliance document, gated more strictly than a plain read."""
        _user, token = _make_user_and_token(
            seeded_session, test_settings, role="client", email="osha-client@example.com",
        )
        response = api_client.get(
            f"{OSHA_URL}?year=2026", headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    def test_owner_role_is_allowed(self, api_client, seeded_session, test_settings):
        _user, token = _make_user_and_token(
            seeded_session, test_settings, role="owner", email="osha-owner@example.com",
        )
        response = api_client.get(
            f"{OSHA_URL}?year=2026", headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"


class TestOshaLogGeneration:
    def test_unknown_project_returns_404(self, api_client, auth_headers):
        response = api_client.get(
            f"/api/v1/projects/{uuid.uuid4()}/osha-300-log?year=2026", headers=auth_headers,
        )
        assert response.status_code == 404

    def test_year_with_no_incidents_returns_a_pdf_with_zero_counts(
        self, api_client, auth_headers
    ):
        response = api_client.get(f"{OSHA_URL}?year=2019", headers=auth_headers)
        assert response.status_code == 200
        assert response.headers["x-osha-log-included-count"] == "0"
        assert response.headers["x-osha-log-needs-review-count"] == "0"
        assert len(response.content) > 0

    def test_complete_incident_is_included(self, api_client, auth_headers, seeded_session):
        worker = Worker(
            company_id=COMPANY_ID, first_name="Case", last_name="Complete",
        )
        seeded_session.add(worker)
        seeded_session.flush()

        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 6, 1), current_stage="framing",
            review_status="approved", total_workers_present=5,
        )
        seeded_session.add(log)
        seeded_session.flush()
        seeded_session.add(LogSafetyIncident(
            daily_log_id=log.id, incident_type="lost_time_injury",
            description="Complete OSHA-ready incident.",
            osha_recordable=True, osha_classification="days_away_from_work",
            injury_illness_type="injury", days_away_from_work_count=5,
            case_number="2026-CASE-1", worker_id=worker.id, worker_match_status="matched",
        ))
        seeded_session.commit()

        response = api_client.get(f"{OSHA_URL}?year=2026", headers=auth_headers)
        assert response.status_code == 200
        assert response.headers["x-osha-log-included-count"] == "1"
        assert response.headers["x-osha-log-needs-review-count"] == "0"

    def test_incomplete_incident_is_excluded_but_counted(
        self, api_client, auth_headers, seeded_session
    ):
        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 6, 2), current_stage="framing",
            review_status="approved", total_workers_present=5,
        )
        seeded_session.add(log)
        seeded_session.flush()
        seeded_session.add(LogSafetyIncident(
            daily_log_id=log.id, incident_type="lost_time_injury",
            description="Recordable but not yet classified.",
            osha_recordable=True, osha_classification=None,
        ))
        seeded_session.commit()

        response = api_client.get(f"{OSHA_URL}?year=2026", headers=auth_headers)
        assert response.status_code == 200
        assert response.headers["x-osha-log-included-count"] == "0"
        assert response.headers["x-osha-log-needs-review-count"] == "1"

    def test_non_recordable_incident_is_excluded(
        self, api_client, auth_headers, seeded_session
    ):
        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 6, 3), current_stage="framing",
            review_status="approved", total_workers_present=5,
        )
        seeded_session.add(log)
        seeded_session.flush()
        seeded_session.add(LogSafetyIncident(
            daily_log_id=log.id, incident_type="near_miss",
            description="Near miss, not OSHA-recordable.",
            osha_recordable=False,
        ))
        seeded_session.commit()

        response = api_client.get(f"{OSHA_URL}?year=2026", headers=auth_headers)
        assert response.status_code == 200
        assert response.headers["x-osha-log-included-count"] == "0"
        assert response.headers["x-osha-log-needs-review-count"] == "0"

    def test_incident_outside_the_requested_year_is_excluded(
        self, api_client, auth_headers, seeded_session
    ):
        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2025, 6, 1), current_stage="framing",
            review_status="approved", total_workers_present=5,
        )
        seeded_session.add(log)
        seeded_session.flush()
        seeded_session.add(LogSafetyIncident(
            daily_log_id=log.id, incident_type="lost_time_injury",
            description="Wrong year.",
            osha_recordable=True, osha_classification="days_away_from_work",
        ))
        seeded_session.commit()

        response = api_client.get(f"{OSHA_URL}?year=2026", headers=auth_headers)
        assert response.status_code == 200
        assert response.headers["x-osha-log-included-count"] == "0"
        assert response.headers["x-osha-log-needs-review-count"] == "0"


class TestTenantIsolation:
    def test_other_companys_incidents_never_appear(
        self, api_client, auth_headers, seeded_session
    ):
        other_company = Company(id=uuid.uuid4(), name="Other Co", slug="other-co-osha-test")
        seeded_session.add(other_company)
        seeded_session.flush()
        other_project = Project(
            id=uuid.uuid4(), company_id=other_company.id, name="Other Project", status="active",
        )
        seeded_session.add(other_project)
        seeded_session.flush()
        other_log = DailyLog(
            id=uuid.uuid4(), project_id=other_project.id,
            log_date=date(2026, 6, 5), current_stage="framing",
            review_status="approved", total_workers_present=3,
        )
        seeded_session.add(other_log)
        seeded_session.flush()
        seeded_session.add(LogSafetyIncident(
            daily_log_id=other_log.id, incident_type="lost_time_injury",
            description="Other company's incident.",
            osha_recordable=True, osha_classification="days_away_from_work",
        ))
        seeded_session.commit()

        response = api_client.get(f"{OSHA_URL}?year=2026", headers=auth_headers)
        assert response.status_code == 200
        assert response.headers["x-osha-log-included-count"] == "0"
