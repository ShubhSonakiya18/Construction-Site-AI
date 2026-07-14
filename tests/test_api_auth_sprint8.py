"""tests/test_api_auth_sprint8.py — Tests for Sprint 8's auth surface:
POST /auth/refresh, /logout, /logout-all, /change-password,
/forgot-password, /reset-password, GET /auth/me.

Sprint 7's own auth tests (tests/test_api_auth.py) still exercise
POST /auth/login unmodified — this file only covers what Sprint 8 added.
"""
from __future__ import annotations

from uuid import UUID

from database.models.auth import UserSession
from database.models.password_reset import PasswordResetToken

pytest_plugins = ["tests.conftest_api"]


def _login(api_client, password: str) -> dict:
    response = api_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


class TestLoginIssuesRefreshToken:
    def test_login_response_includes_refresh_token_and_session_id(
        self, api_client, dev_admin_password_hash
    ):
        data = _login(api_client, dev_admin_password_hash)
        assert data["refresh_token"]
        assert data["refresh_token_expires_in_days"] == 30
        assert data["session_id"]

    def test_login_creates_a_user_session_row(
        self, api_client, dev_admin_password_hash, seeded_session
    ):
        data = _login(api_client, dev_admin_password_hash)
        # seeded_session and api_client's overridden get_db share test_engine
        # (see conftest_api.py) — a fresh query sees the committed row.
        row = seeded_session.get(UserSession, UUID(data["session_id"]))
        assert row is not None
        assert row.is_active

    def test_device_name_is_stored_on_the_session(
        self, api_client, dev_admin_password_hash, seeded_session
    ):
        response = api_client.post(
            "/api/v1/auth/login",
            json={
                "email": "admin@example.com",
                "password": dev_admin_password_hash,
                "device_name": "Test Device",
            },
        )
        session_id = response.json()["data"]["session_id"]
        row = seeded_session.get(UserSession, UUID(session_id))
        assert row.device_name == "Test Device"


class TestRefresh:
    def test_valid_refresh_token_issues_new_pair(self, api_client, dev_admin_password_hash):
        login_data = _login(api_client, dev_admin_password_hash)
        response = api_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login_data["refresh_token"]},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["access_token"]
        assert data["refresh_token"]
        assert data["refresh_token"] != login_data["refresh_token"]
        assert data["session_id"] != login_data["session_id"]

    def test_old_refresh_token_cannot_be_reused_after_rotation(
        self, api_client, dev_admin_password_hash
    ):
        login_data = _login(api_client, dev_admin_password_hash)
        first = api_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": login_data["refresh_token"]}
        )
        assert first.status_code == 200

        second = api_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": login_data["refresh_token"]}
        )
        assert second.status_code == 401
        assert second.json()["success"] is False

    def test_unknown_refresh_token_returns_401(self, api_client):
        response = api_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"}
        )
        assert response.status_code == 401

    def test_new_access_token_is_independently_valid(self, api_client, dev_admin_password_hash):
        login_data = _login(api_client, dev_admin_password_hash)
        refreshed = api_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": login_data["refresh_token"]}
        ).json()["data"]
        me = api_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {refreshed['access_token']}"},
        )
        assert me.status_code == 200


class TestLogout:
    def test_logout_revokes_the_session(self, api_client, dev_admin_password_hash, seeded_session):
        login_data = _login(api_client, dev_admin_password_hash)
        response = api_client.post(
            "/api/v1/auth/logout", json={"refresh_token": login_data["refresh_token"]}
        )
        assert response.status_code == 200
        assert response.json()["data"]["revoked"] is True

        # The revoked token can no longer be used to refresh.
        refresh_attempt = api_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": login_data["refresh_token"]}
        )
        assert refresh_attempt.status_code == 401

    def test_logout_with_unknown_token_is_not_an_error(self, api_client):
        """Idempotent — see AuthService.logout() docstring."""
        response = api_client.post(
            "/api/v1/auth/logout", json={"refresh_token": "never-existed"}
        )
        assert response.status_code == 200


class TestLogoutAll:
    def test_logout_all_revokes_every_session(self, api_client, dev_admin_password_hash):
        # Log in from three "devices."
        sessions = [_login(api_client, dev_admin_password_hash) for _ in range(3)]

        response = api_client.post(
            "/api/v1/auth/logout-all",
            headers={"Authorization": f"Bearer {sessions[0]['access_token']}"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["sessions_revoked"] == 3

        for s in sessions:
            refresh_attempt = api_client.post(
                "/api/v1/auth/refresh", json={"refresh_token": s["refresh_token"]}
            )
            assert refresh_attempt.status_code == 401

    def test_logout_all_requires_authentication(self, api_client):
        response = api_client.post("/api/v1/auth/logout-all")
        assert response.status_code == 401


class TestChangePassword:
    def test_correct_current_password_changes_and_revokes_sessions(
        self, api_client, dev_admin_password_hash
    ):
        login_data = _login(api_client, dev_admin_password_hash)
        response = api_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": dev_admin_password_hash, "new_password": "NewPass456!"},
            headers={"Authorization": f"Bearer {login_data['access_token']}"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["sessions_revoked"] >= 1

        # Old password no longer works; new one does.
        old_login = api_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": dev_admin_password_hash},
        )
        assert old_login.status_code == 401

        new_login = api_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "NewPass456!"},
        )
        assert new_login.status_code == 200

    def test_wrong_current_password_returns_401(self, api_client, dev_admin_password_hash):
        login_data = _login(api_client, dev_admin_password_hash)
        response = api_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "WrongOldPassword", "new_password": "NewPass456!"},
            headers={"Authorization": f"Bearer {login_data['access_token']}"},
        )
        assert response.status_code == 401

    def test_requires_authentication(self, api_client):
        response = api_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "x", "new_password": "NewPass456!"},
        )
        assert response.status_code == 401

    def test_new_password_too_short_returns_422(self, api_client, dev_admin_password_hash):
        login_data = _login(api_client, dev_admin_password_hash)
        response = api_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": dev_admin_password_hash, "new_password": "short"},
            headers={"Authorization": f"Bearer {login_data['access_token']}"},
        )
        assert response.status_code == 422


class TestForgotAndResetPassword:
    def test_forgot_password_known_email_returns_dev_token_in_testing(self, api_client, seeded_session):
        """test_settings fixture sets environment='testing' — see
        conftest_api.py — so AuthService.forgot_password() returns the raw
        token, and this endpoint surfaces it in `metadata` for manual
        verification. Never happens in production (see docstrings)."""
        response = api_client.post(
            "/api/v1/auth/forgot-password", json={"email": "admin@example.com"}
        )
        assert response.status_code == 200
        body = response.json()
        assert "reset link has been sent" in body["message"]
        assert body["metadata"] is not None
        assert body["metadata"]["dev_reset_token"]

    def test_forgot_password_unknown_email_returns_same_generic_message(self, api_client):
        """No account enumeration: unknown email gets the identical
        message and status code as a known one — but no dev token, since
        no token was created."""
        response = api_client.post(
            "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
        )
        assert response.status_code == 200
        body = response.json()
        assert "reset link has been sent" in body["message"]
        assert body["metadata"] is None

    def test_reset_password_with_valid_token_succeeds(self, api_client, seeded_session):
        forgot = api_client.post(
            "/api/v1/auth/forgot-password", json={"email": "admin@example.com"}
        )
        raw_token = forgot.json()["metadata"]["dev_reset_token"]

        response = api_client.post(
            "/api/v1/auth/reset-password",
            json={"reset_token": raw_token, "new_password": "ResetPass789!"},
        )
        assert response.status_code == 200

        login = api_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "ResetPass789!"},
        )
        assert login.status_code == 200

    def test_reset_password_token_is_single_use(self, api_client):
        forgot = api_client.post(
            "/api/v1/auth/forgot-password", json={"email": "admin@example.com"}
        )
        raw_token = forgot.json()["metadata"]["dev_reset_token"]

        first = api_client.post(
            "/api/v1/auth/reset-password",
            json={"reset_token": raw_token, "new_password": "FirstReset123!"},
        )
        assert first.status_code == 200

        second = api_client.post(
            "/api/v1/auth/reset-password",
            json={"reset_token": raw_token, "new_password": "SecondReset456!"},
        )
        assert second.status_code == 401

    def test_reset_password_with_unknown_token_returns_401(self, api_client):
        response = api_client.post(
            "/api/v1/auth/reset-password",
            json={"reset_token": "never-issued", "new_password": "NewPass456!"},
        )
        assert response.status_code == 401

    def test_second_forgot_password_request_invalidates_the_first_token(
        self, api_client, seeded_session
    ):
        """See AuthService.forgot_password(): a newer request revokes any
        still-outstanding earlier token for the same user."""
        first_forgot = api_client.post(
            "/api/v1/auth/forgot-password", json={"email": "admin@example.com"}
        )
        first_token = first_forgot.json()["metadata"]["dev_reset_token"]

        api_client.post("/api/v1/auth/forgot-password", json={"email": "admin@example.com"})

        response = api_client.post(
            "/api/v1/auth/reset-password",
            json={"reset_token": first_token, "new_password": "NewPass456!"},
        )
        assert response.status_code == 401

    def test_reset_password_revokes_all_sessions(self, api_client, dev_admin_password_hash):
        login_data = _login(api_client, dev_admin_password_hash)

        forgot = api_client.post(
            "/api/v1/auth/forgot-password", json={"email": "admin@example.com"}
        )
        raw_token = forgot.json()["metadata"]["dev_reset_token"]
        reset = api_client.post(
            "/api/v1/auth/reset-password",
            json={"reset_token": raw_token, "new_password": "PostResetPass1!"},
        )
        assert reset.json()["data"]["sessions_revoked"] >= 1

        refresh_attempt = api_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": login_data["refresh_token"]}
        )
        assert refresh_attempt.status_code == 401


class TestGetMe:
    def test_returns_current_user(self, api_client, auth_headers):
        response = api_client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["email"] == "admin@example.com"
        assert data["role"] == "owner"

    def test_requires_authentication(self, api_client):
        response = api_client.get("/api/v1/auth/me")
        assert response.status_code == 401
