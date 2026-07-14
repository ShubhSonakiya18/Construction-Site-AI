"""tests/test_core_permissions.py — Unit tests for app/core/permissions.py.

Pure logic, no database or HTTP — see tests/test_api_rbac.py for the
endpoint-level enforcement tests (require_permission() actually blocking
a request).
"""
from __future__ import annotations

from app.core.permissions import (
    ROLE_PERMISSIONS,
    Permission,
    permissions_for_role,
    role_has_permission,
)

_EXISTING_SPRINT6_ROLES = {
    "owner", "admin", "project_manager", "foreman", "safety_officer", "client",
}


class TestExistingRolesPreserved:
    """Sprint 6/7's User.role values must all still be recognized —
    extending the role model must not silently drop one."""

    def test_every_existing_role_has_a_permission_set(self):
        for role in _EXISTING_SPRINT6_ROLES:
            assert role in ROLE_PERMISSIONS, f"{role} missing from ROLE_PERMISSIONS"

    def test_unknown_role_gets_zero_permissions_not_an_exception(self):
        """Fail-closed: a role string not in ROLE_PERMISSIONS (data drift,
        typo, future migration gap) must deny everything, never raise."""
        assert permissions_for_role("not_a_real_role") == frozenset()
        assert role_has_permission("not_a_real_role", Permission.DAILY_LOG_READ) is False


class TestSystemAdminIsNewAndUnrestricted:
    def test_system_admin_is_not_one_of_the_existing_roles(self):
        assert "system_admin" not in _EXISTING_SPRINT6_ROLES

    def test_system_admin_has_every_permission(self):
        for permission in Permission:
            assert role_has_permission("system_admin", permission)


class TestRolePermissionMapping:
    def test_owner_can_approve_and_reject_logs(self):
        assert role_has_permission("owner", Permission.DAILY_LOG_APPROVE)
        assert role_has_permission("owner", Permission.DAILY_LOG_REJECT)

    def test_project_manager_can_approve_and_reject_logs(self):
        """Matches Sprint 7's exact prior hardcoding:
        require_role('owner', 'project_manager') on approve/reject."""
        assert role_has_permission("project_manager", Permission.DAILY_LOG_APPROVE)
        assert role_has_permission("project_manager", Permission.DAILY_LOG_REJECT)

    def test_foreman_cannot_approve_or_reject_logs(self):
        assert not role_has_permission("foreman", Permission.DAILY_LOG_APPROVE)
        assert not role_has_permission("foreman", Permission.DAILY_LOG_REJECT)

    def test_foreman_can_upload_audio_and_submit_logs(self):
        assert role_has_permission("foreman", Permission.AUDIO_UPLOAD)
        assert role_has_permission("foreman", Permission.DAILY_LOG_SUBMIT)

    def test_client_is_read_only_on_daily_logs(self):
        assert role_has_permission("client", Permission.DAILY_LOG_READ)
        assert not role_has_permission("client", Permission.DAILY_LOG_SUBMIT)
        assert not role_has_permission("client", Permission.DAILY_LOG_APPROVE)
        assert not role_has_permission("client", Permission.AUDIO_UPLOAD)

    def test_safety_officer_is_read_only(self):
        assert role_has_permission("safety_officer", Permission.DAILY_LOG_READ)
        assert not role_has_permission("safety_officer", Permission.DAILY_LOG_APPROVE)
        assert not role_has_permission("safety_officer", Permission.USER_CREATE)

    def test_only_owner_admin_and_system_admin_can_manage_users(self):
        for role in ("owner", "admin", "system_admin"):
            assert role_has_permission(role, Permission.USER_CREATE)
        for role in ("project_manager", "foreman", "safety_officer", "client"):
            assert not role_has_permission(role, Permission.USER_CREATE)

    def test_every_role_can_manage_own_sessions(self):
        """SESSION_MANAGE_OWN is granted to every role — logout/refresh
        are self-service, not permission-gated by business role."""
        for role in ROLE_PERMISSIONS:
            assert role_has_permission(role, Permission.SESSION_MANAGE_OWN)
