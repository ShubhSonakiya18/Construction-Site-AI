"""tests/test_api_security_hardening.py — Sprint 8, Subsystem 5 tests.

Covers: account lockout (5 attempts / 15 min, configurable), lockout
clearing on success/password-reset/admin-unlock, rate limiting on
/auth/login and /auth/forgot-password, and security response headers.
"""
from __future__ import annotations

import uuid

from app.core.security import create_access_token, hash_password
from database.seed.sample_data import COMPANY_ID, DEV_ADMIN_ID

pytest_plugins = ["tests.conftest_api"]


def _make_locked_out_user(seeded_session, test_settings, *, email: str, password: str = "CorrectPass123!"):
    from database.models.company import User

    user = User(
        company_id=COMPANY_ID,
        email=email,
        hashed_password=hash_password(password),
        first_name="Lockout",
        last_name="Test",
        role="foreman",
        is_active=True,
    )
    seeded_session.add(user)
    seeded_session.flush()
    seeded_session.commit()
    return user


class TestAccountLockout:
    def test_five_failed_attempts_locks_the_account(self, api_client, seeded_session, test_settings):
        user = _make_locked_out_user(seeded_session, test_settings, email="lockout1@example.com")

        for _ in range(5):
            response = api_client.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": "WrongPassword!"},
            )
            assert response.status_code == 401

        # The 6th attempt — even with the CORRECT password — must now be
        # rejected as locked, not re-verified.
        locked_response = api_client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": "CorrectPass123!"},
        )
        assert locked_response.status_code == 423

    def test_fewer_than_threshold_failures_does_not_lock(self, api_client, seeded_session, test_settings):
        user = _make_locked_out_user(seeded_session, test_settings, email="lockout2@example.com")

        for _ in range(4):
            api_client.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": "WrongPassword!"},
            )

        response = api_client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": "CorrectPass123!"},
        )
        assert response.status_code == 200  # 4 failures is below the 5-attempt threshold

    def test_successful_login_resets_the_failure_counter(self, api_client, seeded_session, test_settings):
        user = _make_locked_out_user(seeded_session, test_settings, email="lockout3@example.com")

        for _ in range(3):
            api_client.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": "WrongPassword!"},
            )
        success = api_client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": "CorrectPass123!"},
        )
        assert success.status_code == 200

        seeded_session.refresh(user)
        assert user.failed_login_attempts == 0
        assert user.locked_until is None

    def test_admin_unlock_clears_lockout(self, api_client, seeded_session, test_settings, auth_headers):
        user = _make_locked_out_user(seeded_session, test_settings, email="lockout4@example.com")
        for _ in range(5):
            api_client.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": "WrongPassword!"},
            )
        still_locked = api_client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": "CorrectPass123!"},
        )
        assert still_locked.status_code == 423

        unlock_response = api_client.post(
            f"/api/v1/users/{user.id}/unlock", headers=auth_headers
        )
        assert unlock_response.status_code == 200

        now_works = api_client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": "CorrectPass123!"},
        )
        assert now_works.status_code == 200

    def test_password_reset_clears_lockout(self, api_client, seeded_session, test_settings):
        user = _make_locked_out_user(seeded_session, test_settings, email="lockout5@example.com")
        for _ in range(5):
            api_client.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": "WrongPassword!"},
            )

        forgot = api_client.post(
            "/api/v1/auth/forgot-password", json={"email": user.email}
        )
        raw_token = forgot.json()["metadata"]["dev_reset_token"]
        reset = api_client.post(
            "/api/v1/auth/reset-password",
            json={"reset_token": raw_token, "new_password": "BrandNewPass456!"},
        )
        assert reset.status_code == 200

        now_works = api_client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": "BrandNewPass456!"},
        )
        assert now_works.status_code == 200

    def test_lockout_does_not_apply_to_nonexistent_email(self, api_client):
        """A nonexistent email has no User row to lock — must keep
        returning 401, never 423 (which would itself be an account-
        enumeration signal: 423 vs 401 reveals whether the email exists)."""
        for _ in range(6):
            response = api_client.post(
                "/api/v1/auth/login",
                json={"email": "never-existed@example.com", "password": "whatever"},
            )
            assert response.status_code == 401


class TestRateLimiting:
    def test_login_rate_limit_returns_429(self, api_client, test_settings):
        # test_settings doesn't override rate_limit_login_attempts, so the
        # Settings default (10) applies — exceed it with a fresh, never-
        # locked-out email so 401s (not 423) are what precede the 429.
        for _ in range(10):
            response = api_client.post(
                "/api/v1/auth/login",
                json={"email": "rate-limit-target@example.com", "password": "whatever"},
            )
            assert response.status_code == 401

        limited = api_client.post(
            "/api/v1/auth/login",
            json={"email": "rate-limit-target@example.com", "password": "whatever"},
        )
        assert limited.status_code == 429

    def test_forgot_password_rate_limit_returns_429(self, api_client):
        for _ in range(3):
            response = api_client.post(
                "/api/v1/auth/forgot-password", json={"email": "rl-forgot@example.com"}
            )
            assert response.status_code == 200

        limited = api_client.post(
            "/api/v1/auth/forgot-password", json={"email": "rl-forgot@example.com"}
        )
        assert limited.status_code == 429

    def test_rate_limit_is_per_email_not_global(self, api_client):
        """Exhausting the limit for one email must not affect a
        different email."""
        for _ in range(3):
            api_client.post(
                "/api/v1/auth/forgot-password", json={"email": "victim-a@example.com"}
            )
        response = api_client.post(
            "/api/v1/auth/forgot-password", json={"email": "victim-b@example.com"}
        )
        assert response.status_code == 200


class TestUnlockPermission:
    def test_foreman_cannot_unlock_accounts(self, api_client, seeded_session, test_settings):
        from database.models.company import User

        foreman = User(
            company_id=COMPANY_ID, email="foreman-nounlock@example.com",
            first_name="F", last_name="Nounlock", role="foreman", is_active=True,
        )
        seeded_session.add(foreman)
        seeded_session.flush()
        seeded_session.commit()
        token = create_access_token(
            subject=str(foreman.id), secret_key=test_settings.jwt_secret_key,
            extra_claims={"company_id": str(COMPANY_ID), "role": "foreman", "email": foreman.email},
        )
        response = api_client.post(
            f"/api/v1/users/{DEV_ADMIN_ID}/unlock",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403


class TestSecurityHeaders:
    def test_response_includes_security_headers(self, api_client):
        response = api_client.get("/api/v1/health")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_hsts_not_sent_in_testing_environment(self, api_client):
        """HSTS is production-only — test_settings has environment='testing'
        (see conftest_api.py), so this header must be absent."""
        response = api_client.get("/api/v1/health")
        assert "Strict-Transport-Security" not in response.headers

    def test_error_responses_also_carry_security_headers(self, api_client):
        """Headers apply to every response, not just success paths —
        SecurityHeadersMiddleware runs on the way out regardless of
        status code."""
        response = api_client.get(f"/api/v1/daily-logs/{uuid.uuid4()}")
        assert response.status_code == 401  # no auth header
        assert response.headers["X-Content-Type-Options"] == "nosniff"
