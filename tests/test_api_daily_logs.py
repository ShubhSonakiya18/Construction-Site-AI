"""
tests/test_api_daily_logs.py — Tests for /api/v1/daily-logs/* and /api/v1/projects/*.

Uses the fixed-UUID sample daily log seeded by database.seed.sample_data
(review_status="approved") as the primary fixture data.
"""
from __future__ import annotations

import uuid

from database.seed.sample_data import DAILY_LOG_ID, PROJECT_ID

pytest_plugins = ["tests.conftest_api"]


class TestGetDailyLog:
    def test_requires_authentication(self, api_client):
        response = api_client.get(f"/api/v1/daily-logs/{DAILY_LOG_ID}")
        assert response.status_code == 401

    def test_returns_full_log_with_children(self, api_client, auth_headers):
        response = api_client.get(
            f"/api/v1/daily-logs/{DAILY_LOG_ID}", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["id"] == str(DAILY_LOG_ID)
        assert data["current_stage"] == "framing"
        assert len(data["trades_on_site"]) == 2
        assert len(data["work_items"]) == 3
        assert len(data["hazards"]) == 1

    def test_nonexistent_log_returns_404(self, api_client, auth_headers):
        response = api_client.get(
            f"/api/v1/daily-logs/{uuid.uuid4()}", headers=auth_headers
        )
        assert response.status_code == 404
        assert response.json()["success"] is False

    def test_invalid_uuid_returns_422(self, api_client, auth_headers):
        response = api_client.get(
            "/api/v1/daily-logs/not-a-uuid", headers=auth_headers
        )
        assert response.status_code == 422


class TestReviewLifecycle:
    def test_submit_on_approved_log_returns_409(self, api_client, auth_headers):
        """The seeded log is already 'approved' — submit_for_review()
        requires 'draft', so this must surface as HTTP 409, not 500."""
        response = api_client.post(
            f"/api/v1/daily-logs/{DAILY_LOG_ID}/submit", headers=auth_headers
        )
        assert response.status_code == 409
        body = response.json()
        assert body["success"] is False
        assert body["errors"][0]["code"] == "business_rule_violation"

    def test_reject_requires_notes_field(self, api_client, auth_headers):
        response = api_client.post(
            f"/api/v1/daily-logs/{DAILY_LOG_ID}/reject",
            json={},
            headers=auth_headers,
        )
        assert response.status_code == 422  # notes is a required field

    def test_approve_requires_owner_or_pm_role(self, api_client, seeded_session, test_settings):
        """The dev-admin seeded user has role='owner', which IS permitted —
        this test constructs a non-privileged token to confirm 403 for a
        role that is NOT owner/project_manager."""
        from app.core.security import create_access_token
        from database.seed.sample_data import COMPANY_ID, FOREMAN_ID

        foreman_token = create_access_token(
            subject=str(FOREMAN_ID),
            secret_key=test_settings.jwt_secret_key,
            extra_claims={
                "company_id": str(COMPANY_ID),
                "role": "foreman",
                "email": "d.rivera@apexresidential.example.com",
            },
        )
        response = api_client.post(
            f"/api/v1/daily-logs/{DAILY_LOG_ID}/approve",
            json={"notes": "Looks good"},
            headers={"Authorization": f"Bearer {foreman_token}"},
        )
        assert response.status_code == 403


class TestGenerationOutputs:
    def test_list_outputs_for_log_with_none_returns_empty_list(self, api_client, auth_headers):
        response = api_client.get(
            f"/api/v1/daily-logs/{DAILY_LOG_ID}/outputs", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["data"] == []

    def test_list_outputs_for_nonexistent_log_returns_404(self, api_client, auth_headers):
        response = api_client.get(
            f"/api/v1/daily-logs/{uuid.uuid4()}/outputs", headers=auth_headers
        )
        assert response.status_code == 404


class TestProjectDailyLogs:
    def test_lists_seeded_log(self, api_client, auth_headers):
        response = api_client.get(
            f"/api/v1/projects/{PROJECT_ID}/daily-logs", headers=auth_headers
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["id"] == str(DAILY_LOG_ID)
        assert body["metadata"]["total"] == 1

    def test_filters_by_status(self, api_client, auth_headers):
        response = api_client.get(
            f"/api/v1/projects/{PROJECT_ID}/daily-logs",
            params={"status": "draft"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["data"] == []  # seeded log is 'approved', not 'draft'

    def test_unknown_project_returns_empty_list_not_error(self, api_client, auth_headers):
        response = api_client.get(
            f"/api/v1/projects/{uuid.uuid4()}/daily-logs", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["data"] == []
