"""tests/test_api_health.py — Tests for GET /api/v1/health(/live|/ready|/version)."""
from __future__ import annotations

pytest_plugins = ["tests.conftest_api"]


class TestLiveness:
    def test_returns_200_always(self, api_client):
        response = api_client.get("/api/v1/health/live")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["status"] == "alive"
        assert "uptime_seconds" in body["data"]

    def test_no_auth_required(self, api_client):
        # No Authorization header sent — must not 401.
        response = api_client.get("/api/v1/health/live")
        assert response.status_code == 200


class TestReadiness:
    def test_ready_when_db_reachable(self, api_client):
        response = api_client.get("/api/v1/health/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["status"] == "ready"
        assert body["data"]["database"] is True


class TestVersion:
    def test_returns_version_metadata(self, api_client):
        response = api_client.get("/api/v1/health/version")
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["environment"] == "testing"
        assert body["data"]["api_version"] == "v1"
        assert "app_version" in body["data"]


class TestEnvelope:
    def test_response_has_standard_envelope_fields(self, api_client):
        response = api_client.get("/api/v1/health/live")
        body = response.json()
        assert set(body.keys()) >= {
            "success", "message", "data", "metadata", "errors", "timestamp", "request_id",
        }

    def test_request_id_header_present_and_matches_body(self, api_client):
        response = api_client.get("/api/v1/health/live")
        header_id = response.headers.get("X-Request-ID")
        body_id = response.json()["request_id"]
        assert header_id is not None
        assert header_id == body_id
