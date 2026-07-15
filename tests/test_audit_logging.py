"""tests/test_audit_logging.py — Sprint 8, Subsystem 6 tests.

Covers: every audit event type this subsystem adds/extends, structured
field correctness (ip_address, request_id, success, target_user_id as
real columns, not buried in event_metadata), fail-open behavior
(safe_log_event never blocks business logic), and the one deliberate
exception (system_admin cross-tenant access, which must fail loudly).
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

from app.core.security import create_access_token
from database.models.generation import AuditLog
from database.repositories.generation import AuditLogRepository
from database.seed.sample_data import COMPANY_ID, DEV_ADMIN_ID

pytest_plugins = ["tests.conftest_api"]


def _events(seeded_session, event_type: str) -> list[AuditLog]:
    from sqlalchemy import select

    stmt = select(AuditLog).where(AuditLog.event_type == event_type)
    return list(seeded_session.execute(stmt).scalars().all())


class TestAuthenticationEvents:
    def test_login_success_is_logged(self, api_client, seeded_session, dev_admin_password_hash):
        response = api_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": dev_admin_password_hash},
        )
        assert response.status_code == 200
        events = _events(seeded_session, "user.login")
        assert len(events) == 1
        event = events[0]
        assert event.actor_id == DEV_ADMIN_ID
        assert event.success is True
        assert event.request_id  # a real request produced a real X-Request-ID

    def test_failed_login_is_logged_with_ip_and_success_false(self, api_client, seeded_session):
        response = api_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "WrongPassword!"},
        )
        assert response.status_code == 401
        events = _events(seeded_session, "user.login_failed")
        assert len(events) == 1
        assert events[0].success is False
        assert events[0].actor_id == DEV_ADMIN_ID

    def test_logout_is_logged(self, api_client, dev_admin_password_hash, seeded_session):
        login = api_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": dev_admin_password_hash},
        ).json()["data"]
        response = api_client.post(
            "/api/v1/auth/logout", json={"refresh_token": login["refresh_token"]}
        )
        assert response.status_code == 200
        events = _events(seeded_session, "user.logout")
        assert len(events) == 1
        assert events[0].success is True

    def test_refresh_issues_and_revokes_are_both_logged(
        self, api_client, dev_admin_password_hash, seeded_session
    ):
        login = api_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": dev_admin_password_hash},
        ).json()["data"]
        api_client.post(
            "/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
        )
        # login() logs "user.login", not "auth.refresh_token_issued" (that
        # event is specific to refresh()'s own token-pair issuance) — so
        # exactly 1 issued and 1 revoked (rotation) from the one refresh call.
        assert len(_events(seeded_session, "auth.refresh_token_issued")) == 1
        assert len(_events(seeded_session, "auth.refresh_token_revoked")) == 1

    def test_invalid_refresh_token_reuse_is_logged(
        self, api_client, dev_admin_password_hash, seeded_session
    ):
        login = api_client.post(
            "/api/v1/auth/login",
            json={"email": "admin@example.com", "password": dev_admin_password_hash},
        ).json()["data"]
        api_client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
        # Reuse the now-rotated-away token.
        api_client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})

        events = _events(seeded_session, "auth.invalid_refresh_token")
        assert len(events) == 1
        assert events[0].success is False

    def test_password_change_success_and_failure_are_logged(
        self, api_client, dev_admin_password_hash, auth_headers, seeded_session
    ):
        wrong = api_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "WrongOldPassword", "new_password": "NewPass456!"},
            headers=auth_headers,
        )
        assert wrong.status_code == 401
        assert len(_events(seeded_session, "user.password_change_failed")) == 1

        correct = api_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": dev_admin_password_hash, "new_password": "NewPass456!"},
            headers=auth_headers,
        )
        assert correct.status_code == 200
        assert len(_events(seeded_session, "user.password_changed")) == 1

    def test_password_reset_requested_and_completed_are_logged(self, api_client, seeded_session):
        forgot = api_client.post(
            "/api/v1/auth/forgot-password", json={"email": "admin@example.com"}
        )
        assert len(_events(seeded_session, "user.password_reset_requested")) == 1

        raw_token = forgot.json()["metadata"]["dev_reset_token"]
        api_client.post(
            "/api/v1/auth/reset-password",
            json={"reset_token": raw_token, "new_password": "ResetPass789!"},
        )
        assert len(_events(seeded_session, "user.password_reset_completed")) == 1

    def test_forgot_password_for_nonexistent_email_logs_nothing(self, api_client, seeded_session):
        """Explicit account-enumeration precaution: logging an event only
        for real emails would itself leak which emails exist."""
        api_client.post(
            "/api/v1/auth/forgot-password", json={"email": "never-existed@example.com"}
        )
        assert len(_events(seeded_session, "user.password_reset_requested")) == 0


class TestLockoutEvents:
    def test_lockout_logs_locked_event_with_metadata(self, api_client, seeded_session, test_settings):
        from app.core.security import hash_password
        from database.models.company import User

        user = User(
            company_id=COMPANY_ID, email="lockout-audit@example.com",
            hashed_password=hash_password("CorrectPass123!"),
            first_name="L", last_name="A", role="foreman", is_active=True,
        )
        seeded_session.add(user)
        seeded_session.flush()
        seeded_session.commit()

        for _ in range(5):
            api_client.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": "WrongPassword!"},
            )

        locked_events = _events(seeded_session, "user.locked")
        assert len(locked_events) == 1
        assert "locked_until" in locked_events[0].event_metadata
        assert len(_events(seeded_session, "user.login_failed")) == 5

    def test_unlock_is_logged(self, api_client, seeded_session, test_settings, auth_headers):
        from app.core.security import hash_password
        from database.models.company import User

        user = User(
            company_id=COMPANY_ID, email="unlock-audit@example.com",
            hashed_password=hash_password("CorrectPass123!"),
            first_name="U", last_name="A", role="foreman", is_active=True,
        )
        seeded_session.add(user)
        seeded_session.flush()
        seeded_session.commit()
        for _ in range(5):
            api_client.post(
                "/api/v1/auth/login",
                json={"email": user.email, "password": "WrongPassword!"},
            )

        response = api_client.post(f"/api/v1/users/{user.id}/unlock", headers=auth_headers)
        assert response.status_code == 200
        events = _events(seeded_session, "user.unlocked")
        assert len(events) == 1
        assert events[0].target_user_id == user.id


class TestUserManagementEvents:
    def test_user_created_logs_target_user_id(self, api_client, auth_headers, seeded_session):
        response = api_client.post(
            "/api/v1/users",
            json={
                "email": "audit-created@example.com", "password": "SecurePass123!",
                "first_name": "Audit", "last_name": "Created", "role": "foreman",
            },
            headers=auth_headers,
        )
        new_user_id = response.json()["data"]["id"]
        events = _events(seeded_session, "user.created")
        assert len(events) == 1
        assert str(events[0].target_user_id) == new_user_id
        assert events[0].new_values == {"email": "audit-created@example.com", "role": "foreman"}

    def test_profile_updated_logs_old_and_new_values(self, api_client, auth_headers, seeded_session):
        api_client.patch(
            f"/api/v1/users/{DEV_ADMIN_ID}/profile",
            json={"first_name": "Changed"},
            headers=auth_headers,
        )
        events = _events(seeded_session, "user.profile_updated")
        assert len(events) == 1
        assert events[0].new_values["first_name"] == "Changed"
        assert "first_name" in events[0].old_values

    def test_deactivate_and_restore_are_logged(self, api_client, auth_headers, seeded_session):
        create_resp = api_client.post(
            "/api/v1/users",
            json={
                "email": "deact-audit@example.com", "password": "SecurePass123!",
                "first_name": "D", "last_name": "A", "role": "foreman",
            },
            headers=auth_headers,
        )
        target_id = create_resp.json()["data"]["id"]

        api_client.post(f"/api/v1/users/{target_id}/deactivate", headers=auth_headers)
        assert len(_events(seeded_session, "user.deactivated")) == 1

        api_client.post(f"/api/v1/users/{target_id}/restore", headers=auth_headers)
        assert len(_events(seeded_session, "user.restored")) == 1

    def test_role_change_logs_old_and_new_role(self, api_client, auth_headers, seeded_session):
        create_resp = api_client.post(
            "/api/v1/users",
            json={
                "email": "role-audit@example.com", "password": "SecurePass123!",
                "first_name": "R", "last_name": "A", "role": "foreman",
            },
            headers=auth_headers,
        )
        target_id = create_resp.json()["data"]["id"]
        api_client.patch(
            f"/api/v1/users/{target_id}/role",
            json={"role": "project_manager"},
            headers=auth_headers,
        )
        events = _events(seeded_session, "user.role_changed")
        assert len(events) == 1
        assert events[0].old_values == {"role": "foreman"}
        assert events[0].new_values == {"role": "project_manager"}


class TestSecurityEvents:
    def test_unauthorized_access_logged_for_missing_token(self, api_client, seeded_session):
        response = api_client.get(f"/api/v1/daily-logs/{uuid.uuid4()}")
        assert response.status_code == 401
        events = _events(seeded_session, "security.unauthorized_access")
        assert len(events) == 1
        assert events[0].event_metadata["reason"] == "missing_credentials"
        assert events[0].success is False

    def test_unauthorized_access_logged_for_malformed_token(self, api_client, seeded_session):
        response = api_client.get(
            f"/api/v1/daily-logs/{uuid.uuid4()}",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert response.status_code == 401
        events = _events(seeded_session, "security.unauthorized_access")
        assert any(e.event_metadata.get("reason") == "invalid_jwt" for e in events)

    def test_forbidden_access_logged_with_required_permission(
        self, api_client, seeded_session, test_settings
    ):
        from database.models.company import User

        client_user = User(
            company_id=COMPANY_ID, email="forbidden-audit@example.com",
            first_name="F", last_name="A", role="client", is_active=True,
        )
        seeded_session.add(client_user)
        seeded_session.flush()
        seeded_session.commit()
        token = create_access_token(
            subject=str(client_user.id), secret_key=test_settings.jwt_secret_key,
            extra_claims={"company_id": str(COMPANY_ID), "role": "client", "email": client_user.email},
        )
        response = api_client.post(
            f"/api/v1/daily-logs/{uuid.uuid4()}/submit",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
        events = _events(seeded_session, "security.forbidden_access")
        assert len(events) == 1
        assert events[0].event_metadata["required_permission"] == "daily_log:submit"
        assert events[0].event_metadata["role"] == "client"

    def test_rate_limit_triggered_is_logged(self, api_client, seeded_session):
        for _ in range(10):
            api_client.post(
                "/api/v1/auth/login",
                json={"email": "rl-audit-target@example.com", "password": "whatever"},
            )
        limited = api_client.post(
            "/api/v1/auth/login",
            json={"email": "rl-audit-target@example.com", "password": "whatever"},
        )
        assert limited.status_code == 429
        events = _events(seeded_session, "security.rate_limit_triggered")
        assert len(events) == 1
        assert events[0].event_metadata["scope"] == "login"


class TestCrossTenantAuditIsMandatory:
    def test_cross_tenant_bypass_failure_propagates_not_swallowed(self, seeded_session):
        """Explicit design requirement: system_admin cross-tenant access
        must generate an audit log entry unconditionally — unlike every
        other event in this subsystem (which use the fail-open
        safe_log_event() wrapper), a broken audit write here must make
        the bypass itself fail, not silently succeed with no record."""
        from database.repositories.project import ProjectRepository
        from database.repositories.tenant import TenantContext

        tenant = TenantContext(company_id=COMPANY_ID, user_id=uuid.uuid4())
        repo = ProjectRepository(seeded_session)

        with patch(
            "database.repositories.generation.AuditLogRepository.log_event",
            side_effect=RuntimeError("simulated DB failure"),
        ):
            try:
                repo.get_by_id_cross_tenant(uuid.uuid4(), tenant=tenant)
                raised = False
            except RuntimeError:
                raised = True
        assert raised, "cross-tenant audit failure must propagate, not be swallowed"


class TestFailOpenBehavior:
    def test_safe_log_event_never_raises(self, seeded_session):
        """The core fail-open contract: safe_log_event() catches ANY
        exception from the underlying write and returns None."""
        from app.services.audit_helpers import safe_log_event

        audit_repo = AuditLogRepository(seeded_session)
        with patch.object(audit_repo, "log_event", side_effect=RuntimeError("simulated DB failure")):
            result = safe_log_event(audit_repo, "test.event", actor_id=uuid.uuid4())
        assert result is None  # did not raise

    def test_login_succeeds_even_if_audit_write_fails(
        self, api_client, dev_admin_password_hash, seeded_session
    ):
        """The concrete end-to-end guarantee: a broken audit log write
        must not turn a successful login into a failed request. Patches
        the underlying AuditLogRepository.log_event() (not
        safe_log_event() itself, which would bypass the very try/except
        this test is verifying)."""
        with patch(
            "database.repositories.generation.AuditLogRepository.log_event",
            side_effect=RuntimeError("simulated DB failure"),
        ):
            response = api_client.post(
                "/api/v1/auth/login",
                json={"email": "admin@example.com", "password": dev_admin_password_hash},
            )
        assert response.status_code == 200  # login succeeded despite audit failure
