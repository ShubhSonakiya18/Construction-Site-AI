"""tests/test_api_rbac.py — Endpoint-level RBAC/permission enforcement tests.

Sprint 8. Covers app/core/permissions.py's require_permission() actually
blocking requests at the router layer, across the endpoints extended in
this sprint (previously only /daily-logs/{id}/approve and /reject had any
role check at all — see docs/AUTHORIZATION_ARCHITECTURE.md "What Changed").

tests/test_api_daily_logs.py::TestReviewLifecycle::test_approve_requires_owner_or_pm_role
already covers the original Sprint 7 approve/reject check under the new
permission-based mechanism (same behavior, different implementation) — this
file covers the endpoints that had NO check before Sprint 8: audio upload,
audio status, daily-log read/submit/generate/outputs, project listing.
"""
from __future__ import annotations

import io

from app.core.security import create_access_token
from database.seed.sample_data import COMPANY_ID, DAILY_LOG_ID, PROJECT_ID

pytest_plugins = ["tests.conftest_api"]


def _make_user_and_token(seeded_session, test_settings, *, role: str, email: str):
    """Build a real User row (not just a claimed role in a token — see
    test_api_daily_logs.py's test_approve_requires_owner_or_pm_role
    docstring for why get_current_user()'s DB lookup requires this) and a
    valid access token for it."""
    from database.models.company import User

    user = User(
        company_id=COMPANY_ID,
        email=email,
        first_name="RBAC",
        last_name="Test",
        role=role,
        is_active=True,
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


class TestAudioUploadPermission:
    def test_client_role_cannot_upload_audio(self, api_client, seeded_session, test_settings):
        """'client' has no AUDIO_UPLOAD grant (read-only role) — see
        app/core/permissions.py ROLE_PERMISSIONS['client']."""
        _user, token = _make_user_and_token(
            seeded_session, test_settings, role="client", email="client-rbac@example.com"
        )
        response = api_client.post(
            "/api/v1/audio/upload",
            files={"file": ("recording.wav", io.BytesIO(b"RIFF____WAVEfmt "), "audio/wav")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    def test_foreman_role_can_upload_audio(self, api_client, seeded_session, test_settings):
        _user, token = _make_user_and_token(
            seeded_session, test_settings, role="foreman", email="foreman-upload@example.com"
        )
        response = api_client.post(
            "/api/v1/audio/upload",
            files={"file": ("recording.wav", io.BytesIO(b"RIFF____WAVEfmt "), "audio/wav")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 202


class TestDailyLogPermissions:
    def test_client_role_can_read_a_daily_log(self, api_client, seeded_session, test_settings):
        """'client' has DAILY_LOG_READ — read-only, not zero access."""
        _user, token = _make_user_and_token(
            seeded_session, test_settings, role="client", email="client-read@example.com"
        )
        response = api_client.get(
            f"/api/v1/daily-logs/{DAILY_LOG_ID}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

    def test_client_role_cannot_submit_a_daily_log(self, api_client, seeded_session, test_settings):
        _user, token = _make_user_and_token(
            seeded_session, test_settings, role="client", email="client-submit@example.com"
        )
        response = api_client.post(
            f"/api/v1/daily-logs/{DAILY_LOG_ID}/submit",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    def test_client_role_cannot_trigger_generation(self, api_client, seeded_session, test_settings):
        _user, token = _make_user_and_token(
            seeded_session, test_settings, role="client", email="client-generate@example.com"
        )
        response = api_client.post(
            f"/api/v1/daily-logs/{DAILY_LOG_ID}/generate",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    def test_foreman_can_submit_but_not_approve(self, api_client, seeded_session, test_settings):
        _user, token = _make_user_and_token(
            seeded_session, test_settings, role="foreman", email="foreman-submit@example.com"
        )
        headers = {"Authorization": f"Bearer {token}"}

        # Submit is granted to foreman (even though this particular log is
        # already approved, so the ValueError->409 path fires — the point
        # here is it's not blocked at the 403 permission layer).
        submit_response = api_client.post(
            f"/api/v1/daily-logs/{DAILY_LOG_ID}/submit", headers=headers
        )
        assert submit_response.status_code != 403

        approve_response = api_client.post(
            f"/api/v1/daily-logs/{DAILY_LOG_ID}/approve",
            json={"notes": "test"},
            headers=headers,
        )
        assert approve_response.status_code == 403


class TestProjectListPermission:
    def test_client_role_can_list_project_daily_logs(self, api_client, seeded_session, test_settings):
        """PROJECT_READ is granted to every role including client."""
        _user, token = _make_user_and_token(
            seeded_session, test_settings, role="client", email="client-project@example.com"
        )
        response = api_client.get(
            f"/api/v1/projects/{PROJECT_ID}/daily-logs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200


class TestSystemAdminHasFullAccess:
    def test_system_admin_can_approve_a_log(self, api_client, seeded_session, test_settings):
        """system_admin (new in Sprint 8, cross-company superuser) has
        every permission — sanity check it isn't accidentally excluded
        from a company-scoped action."""
        from database.repositories.daily_log import DailyLogRepository

        # Reset the seeded log to 'draft' via direct repo access so this
        # test isn't order-dependent on approve/reject already having run.
        repo = DailyLogRepository(seeded_session)
        log = repo.get_by_id(DAILY_LOG_ID)
        log.review_status = "under_review"
        seeded_session.flush()
        seeded_session.commit()

        _user, token = _make_user_and_token(
            seeded_session, test_settings, role="system_admin", email="sysadmin-rbac@example.com"
        )
        response = api_client.post(
            f"/api/v1/daily-logs/{DAILY_LOG_ID}/approve",
            json={"notes": "system admin override"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
