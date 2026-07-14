"""
tests/test_api_auth_lifecycle.py — Tests for get_current_user()'s user
existence/active-state verification (app/api/dependencies.py).

Covers a real bug found by live critical testing: a syntactically valid,
correctly-signed JWT whose subject does not resolve to a live, active User
row crashed downstream endpoints with an unhandled
psycopg2.errors.ForeignKeyViolation (500, leaking a raw SQL traceback to
the client) instead of failing authentication cleanly. Confirmed live via
POST /api/v1/audio/upload with a token naming a UUID that had never been a
User row — the same failure mode a soft-deleted or deactivated user's
still-valid token falls into.

Fix: get_current_user() now looks the user up via UserRepository.get_by_id()
(excludes soft-deleted rows by default) and additionally checks is_active,
raising a uniform 401 for every invalid-user case — deleted, deactivated,
or never existed — never distinguishing between them in the response (see
that function's docstring for the "why" on both the DB check and the
uniform message).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from database.models.company import User
from database.seed.sample_data import COMPANY_ID, DAILY_LOG_ID

from app.core.security import create_access_token

pytest_plugins = ["tests.conftest_api"]


def _craft_token(subject: str, test_settings, role: str = "foreman", expires_minutes: int = 60) -> str:
    return create_access_token(
        subject=subject,
        secret_key=test_settings.jwt_secret_key,
        algorithm=test_settings.jwt_algorithm,
        expires_minutes=expires_minutes,
        extra_claims={"company_id": str(COMPANY_ID), "role": role, "email": "x@example.com"},
    )


class TestUserLifecycleAuth:
    def test_valid_token_existing_active_user_succeeds(self, api_client, auth_headers):
        """Scenario 1: valid token + existing active user -> 200."""
        response = api_client.get(f"/api/v1/daily-logs/{DAILY_LOG_ID}", headers=auth_headers)
        assert response.status_code == 200

    def test_valid_token_soft_deleted_user_returns_401_not_500(
        self, api_client, seeded_session, test_settings
    ):
        """Scenario 2: valid token + soft-deleted user -> 401, not 500.

        Reproduces the exact bug class: the user existed when the token was
        issued, then was soft-deleted — the token is still cryptographically
        valid for up to jwt_access_token_expire_minutes."""
        deleted_user = User(
            company_id=COMPANY_ID, email="deleted@example.com",
            first_name="Deleted", last_name="User", role="foreman", is_active=True,
        )
        seeded_session.add(deleted_user)
        seeded_session.flush()
        deleted_user.deleted_at = datetime.now(timezone.utc)
        seeded_session.commit()

        token = _craft_token(str(deleted_user.id), test_settings)
        response = api_client.get(
            f"/api/v1/daily-logs/{DAILY_LOG_ID}", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401
        assert "Traceback" not in response.text
        assert "psycopg2" not in response.text
        assert "sqlite3" not in response.text

    def test_valid_token_inactive_user_returns_401_not_500(
        self, api_client, seeded_session, test_settings
    ):
        """Scenario 3: valid token + inactive (is_active=False) user -> 401, not 500."""
        inactive_user = User(
            company_id=COMPANY_ID, email="inactive@example.com",
            first_name="Inactive", last_name="User", role="foreman", is_active=False,
        )
        seeded_session.add(inactive_user)
        seeded_session.flush()
        seeded_session.commit()

        token = _craft_token(str(inactive_user.id), test_settings)
        response = api_client.get(
            f"/api/v1/daily-logs/{DAILY_LOG_ID}", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401

    def test_valid_token_nonexistent_user_returns_401_not_500(self, api_client, test_settings):
        """Scenario 4: valid token + a subject that was never a User row -> 401, not 500.

        This IS the original bug's exact reproduction: a syntactically
        valid, correctly-signed JWT whose 'sub' claim does not resolve to
        any User row at all. Before the fix, get_current_user() trusted the
        claims unconditionally and downstream code crashed the first time
        it tried to write that non-existent user_id into a real FK column."""
        never_existed_id = str(uuid.uuid4())
        token = _craft_token(never_existed_id, test_settings)
        response = api_client.get(
            f"/api/v1/daily-logs/{DAILY_LOG_ID}", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401
        assert "Traceback" not in response.text

    def test_nonexistent_user_token_on_audio_upload_returns_401_not_500(
        self, api_client, test_settings
    ):
        """The exact endpoint the original bug was found on: POST
        /audio/upload writes user.user_id into AudioFile.uploaded_by_id, a
        real FK to users.id. Before the fix this crashed with
        IntegrityError -> unhandled 500. Confirmed fixed."""
        import io

        never_existed_id = str(uuid.uuid4())
        token = _craft_token(never_existed_id, test_settings)
        response = api_client.post(
            "/api/v1/audio/upload",
            files={"file": ("t.wav", io.BytesIO(b"RIFF"), "audio/wav")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert "psycopg2" not in response.text
        assert "IntegrityError" not in response.text

    def test_malformed_token_returns_401(self, api_client):
        """Scenario 5: invalid/malformed token -> 401."""
        response = api_client.get(
            f"/api/v1/daily-logs/{DAILY_LOG_ID}",
            headers={"Authorization": "Bearer not.a.valid.jwt"},
        )
        assert response.status_code == 401

    def test_expired_token_returns_401(self, api_client, seeded_session, test_settings):
        """Scenario 6: expired token (valid user, but token TTL elapsed) -> 401."""
        from database.seed.sample_data import DEV_ADMIN_ID

        token = _craft_token(str(DEV_ADMIN_ID), test_settings, role="owner", expires_minutes=-5)
        response = api_client.get(
            f"/api/v1/daily-logs/{DAILY_LOG_ID}", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401

    def test_deleted_inactive_and_nonexistent_return_identical_message(
        self, api_client, seeded_session, test_settings
    ):
        """No response should reveal WHY authentication failed (deleted vs
        deactivated vs never existed) — see get_current_user()'s docstring
        for the account-enumeration rationale, matching the existing
        login-endpoint precedent (app/api/v1/auth.py)."""
        deleted_user = User(
            company_id=COMPANY_ID, email="deleted2@example.com",
            first_name="Deleted2", last_name="User", role="foreman", is_active=True,
        )
        seeded_session.add(deleted_user)
        seeded_session.flush()
        deleted_user.deleted_at = datetime.now(timezone.utc)

        inactive_user = User(
            company_id=COMPANY_ID, email="inactive2@example.com",
            first_name="Inactive2", last_name="User", role="foreman", is_active=False,
        )
        seeded_session.add(inactive_user)
        seeded_session.flush()
        seeded_session.commit()

        messages = set()
        for subject in [str(deleted_user.id), str(inactive_user.id), str(uuid.uuid4())]:
            token = _craft_token(subject, test_settings)
            response = api_client.get(
                f"/api/v1/daily-logs/{DAILY_LOG_ID}", headers={"Authorization": f"Bearer {token}"}
            )
            body = response.json()
            messages.add(body.get("errors", [{}])[0].get("message", body.get("message", "")))

        assert len(messages) == 1, f"Expected one uniform message, got: {messages}"
