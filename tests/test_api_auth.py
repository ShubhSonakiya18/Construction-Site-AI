"""tests/test_api_auth.py — Tests for POST /api/v1/auth/login."""
from __future__ import annotations

from app.core.security import decode_access_token
from tests.conftest_api import TEST_JWT_SECRET

pytest_plugins = ["tests.conftest_api"]


class TestLoginSuccess:
    def test_correct_credentials_returns_token(self, api_client, dev_admin_password_hash):
        response = api_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": dev_admin_password_hash},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["token_type"] == "bearer"
        assert body["data"]["role"] == "owner"
        assert body["data"]["email"] == "admin@example.com"

    def test_token_contains_expected_claims(self, api_client, dev_admin_password_hash):
        response = api_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": dev_admin_password_hash},
        )
        token = response.json()["data"]["access_token"]
        claims = decode_access_token(token, secret_key=TEST_JWT_SECRET)
        assert claims is not None
        assert claims["role"] == "owner"
        assert "company_id" in claims
        assert claims["email"] == "admin@example.com"


class TestLoginFailure:
    def test_wrong_password_returns_401(self, api_client, dev_admin_password_hash):
        response = api_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "WrongPassword"},
        )
        assert response.status_code == 401
        body = response.json()
        assert body["success"] is False

    def test_nonexistent_email_returns_401_not_404(self, api_client, seeded_session):
        """Same error for 'no such user' as for 'wrong password' — avoids
        account enumeration (see app/api/v1/auth.py comment)."""
        response = api_client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "whatever"},
        )
        assert response.status_code == 401

    def test_user_with_null_hashed_password_cannot_login(self, api_client, seeded_session):
        """The seeded owner@apexresidential.example.com user has
        hashed_password=None (Sprint 8 territory) — must fail cleanly,
        not crash with a passlib error."""
        response = api_client.post(
            "/api/v1/auth/login",
            json={"email": "owner@apexresidential.example.com", "password": "anything"},
        )
        assert response.status_code == 401

    def test_malformed_request_returns_422(self, api_client):
        response = api_client.post("/api/v1/auth/login", json={"email": "not-an-email"})
        assert response.status_code == 422
        body = response.json()
        assert body["success"] is False
        assert body["errors"] is not None
