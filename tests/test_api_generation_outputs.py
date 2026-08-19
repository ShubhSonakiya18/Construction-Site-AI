"""
tests/test_api_generation_outputs.py — Sprint 10: POST
/daily-logs/{id}/outputs/{output_id}/mark-sent.

Tracks that a generated document (typically the customer update) was
sent — GenerationOutput.is_sent/sent_at existed since Sprint 6 but this
is the first endpoint that ever sets them. Does not send anything itself
(see docs/NEXT_SPRINT.md Deliverable 3 for why).
"""
from __future__ import annotations

import uuid

import pytest

from database.models.generation import GenerationOutput
from database.seed.sample_data import DAILY_LOG_ID

pytest_plugins = ["tests.conftest_api"]


@pytest.fixture
def unsent_output(seeded_session):
    output = GenerationOutput(
        daily_log_id=DAILY_LOG_ID,
        service_type="customer_update",
        generation_id=uuid.uuid4(),
        content="Subject: Project Update\n\nGreat progress this week.",
        is_valid=True,
        is_sent=False,
    )
    seeded_session.add(output)
    seeded_session.commit()
    return output


def _mark_sent_url(log_id, output_id) -> str:
    return f"/api/v1/daily-logs/{log_id}/outputs/{output_id}/mark-sent"


def test_requires_authentication(api_client, unsent_output):
    response = api_client.post(_mark_sent_url(DAILY_LOG_ID, unsent_output.id))
    assert response.status_code == 401


def test_marks_output_as_sent(api_client, auth_headers, unsent_output):
    response = api_client.post(
        _mark_sent_url(DAILY_LOG_ID, unsent_output.id), headers=auth_headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data"]["is_sent"] is True
    assert "Marked as sent" in body["message"]


def test_marking_an_already_sent_output_is_idempotent(
    api_client, auth_headers, unsent_output
):
    first = api_client.post(
        _mark_sent_url(DAILY_LOG_ID, unsent_output.id), headers=auth_headers
    )
    assert first.json()["message"] == "Marked as sent."

    second = api_client.post(
        _mark_sent_url(DAILY_LOG_ID, unsent_output.id), headers=auth_headers
    )
    assert second.status_code == 200
    assert second.json()["data"]["is_sent"] is True
    assert second.json()["message"] == "Already marked as sent."


def test_nonexistent_output_returns_404(api_client, auth_headers):
    response = api_client.post(
        _mark_sent_url(DAILY_LOG_ID, uuid.uuid4()), headers=auth_headers
    )
    assert response.status_code == 404


def test_nonexistent_log_returns_404(api_client, auth_headers, unsent_output):
    response = api_client.post(
        _mark_sent_url(uuid.uuid4(), unsent_output.id), headers=auth_headers
    )
    assert response.status_code == 404


def test_output_belonging_to_a_different_log_returns_404(
    api_client, auth_headers, seeded_session, unsent_output
):
    """Guards the two-step tenant-scoping pattern: an output_id that is
    real but belongs to a DIFFERENT daily log must not be mark-able via
    this log's URL — even if that other log happens to belong to the
    same company."""
    from datetime import date

    from database.models.company import Company
    from database.models.daily_log import DailyLog
    from database.models.project import Project

    other_company = Company(
        id=uuid.uuid4(), name="Other Co", slug="other-co-outputs-test",
    )
    seeded_session.add(other_company)
    seeded_session.flush()
    other_project = Project(
        id=uuid.uuid4(), company_id=other_company.id, name="Other Project", status="active",
    )
    seeded_session.add(other_project)
    seeded_session.flush()
    other_log = DailyLog(
        id=uuid.uuid4(), project_id=other_project.id,
        log_date=date(2026, 1, 1), current_stage="site_preparation",
        review_status="approved", total_workers_present=0,
    )
    seeded_session.add(other_log)
    seeded_session.commit()

    response = api_client.post(
        _mark_sent_url(other_log.id, unsent_output.id), headers=auth_headers
    )
    assert response.status_code == 404


class TestPermission:
    def test_role_without_daily_log_send_output_permission_gets_403(
        self, api_client, seeded_session, test_settings, unsent_output
    ):
        from app.core.security import hash_password
        from database.models.company import User
        from database.seed.sample_data import COMPANY_ID

        client_user = User(
            id=uuid.uuid4(), company_id=COMPANY_ID,
            email="client-role-test@example.com",
            hashed_password=hash_password("ClientPass123"),
            first_name="Cli", last_name="Ent", role="client", is_active=True,
        )
        seeded_session.add(client_user)
        seeded_session.commit()

        login = api_client.post(
            "/api/v1/auth/login",
            json={"email": "client-role-test@example.com", "password": "ClientPass123"},
        )
        token = login.json()["data"]["access_token"]

        response = api_client.post(
            _mark_sent_url(DAILY_LOG_ID, unsent_output.id),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
