"""tests/test_api_users.py — Tests for /api/v1/users/* (Sprint 8, Subsystem 4).

Covers: creation, listing, profile update, deactivate/restore, and role
assignment (self-assignment block, hierarchy enforcement, last-admin
protection). Tenant isolation for these endpoints is covered separately in
tests/test_multi_tenant_isolation.py's pattern — a couple of cross-tenant
spot checks are included here too since user management is a new surface.
"""
from __future__ import annotations

import uuid

from app.core.security import create_access_token
from database.seed.sample_data import COMPANY_ID

pytest_plugins = ["tests.conftest_api"]


def _make_user_and_token(seeded_session, test_settings, *, company_id, role: str, email: str):
    from database.models.company import User

    user = User(
        company_id=company_id,
        email=email,
        first_name="Test",
        last_name="User",
        role=role,
        is_active=True,
    )
    seeded_session.add(user)
    seeded_session.flush()
    seeded_session.commit()

    token = create_access_token(
        subject=str(user.id),
        secret_key=test_settings.jwt_secret_key,
        extra_claims={"company_id": str(company_id), "role": role, "email": email},
    )
    return user, token


class TestCreateUser:
    def test_owner_can_create_a_user(self, api_client, auth_headers):
        response = api_client.post(
            "/api/v1/users",
            json={
                "email": "newuser@example.com", "password": "SecurePass123!",
                "first_name": "New", "last_name": "User", "role": "foreman",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["email"] == "newuser@example.com"
        assert data["role"] == "foreman"
        assert data["company_id"] == str(COMPANY_ID)

    def test_duplicate_email_returns_409(self, api_client, auth_headers):
        payload = {
            "email": "dup@example.com", "password": "SecurePass123!",
            "first_name": "A", "last_name": "B", "role": "foreman",
        }
        first = api_client.post("/api/v1/users", json=payload, headers=auth_headers)
        assert first.status_code == 201
        second = api_client.post("/api/v1/users", json=payload, headers=auth_headers)
        assert second.status_code == 409

    def test_foreman_cannot_create_users(self, api_client, seeded_session, test_settings):
        _user, token = _make_user_and_token(
            seeded_session, test_settings, company_id=COMPANY_ID, role="foreman",
            email="foreman-nocreate@example.com",
        )
        response = api_client.post(
            "/api/v1/users",
            json={
                "email": "blocked@example.com", "password": "SecurePass123!",
                "first_name": "X", "last_name": "Y", "role": "client",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    def test_cannot_create_system_admin_via_endpoint(self, api_client, auth_headers):
        response = api_client.post(
            "/api/v1/users",
            json={
                "email": "wannabe-admin@example.com", "password": "SecurePass123!",
                "first_name": "X", "last_name": "Y", "role": "system_admin",
            },
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_weak_password_returns_422(self, api_client, auth_headers):
        response = api_client.post(
            "/api/v1/users",
            json={
                "email": "weak@example.com", "password": "short",
                "first_name": "X", "last_name": "Y", "role": "foreman",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestListAndGetUser:
    def test_list_users_returns_seeded_users(self, api_client, auth_headers):
        response = api_client.get("/api/v1/users", headers=auth_headers)
        assert response.status_code == 200
        assert len(response.json()["data"]) >= 1

    def test_get_own_company_user(self, api_client, auth_headers, seeded_session):
        from database.seed.sample_data import DEV_ADMIN_ID

        response = api_client.get(f"/api/v1/users/{DEV_ADMIN_ID}", headers=auth_headers)
        assert response.status_code == 200

    def test_get_nonexistent_user_returns_404(self, api_client, auth_headers):
        response = api_client.get(f"/api/v1/users/{uuid.uuid4()}", headers=auth_headers)
        assert response.status_code == 404


class TestProfileUpdate:
    def test_update_first_and_last_name(self, api_client, auth_headers, seeded_session):
        from database.seed.sample_data import DEV_ADMIN_ID

        response = api_client.patch(
            f"/api/v1/users/{DEV_ADMIN_ID}/profile",
            json={"first_name": "Updated", "last_name": "Name"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["first_name"] == "Updated"
        assert data["last_name"] == "Name"


class TestDeactivateAndRestore:
    def test_deactivate_and_restore_cycle(self, api_client, auth_headers, seeded_session, test_settings):
        create_resp = api_client.post(
            "/api/v1/users",
            json={
                "email": "todeactivate@example.com", "password": "SecurePass123!",
                "first_name": "To", "last_name": "Deactivate", "role": "foreman",
            },
            headers=auth_headers,
        )
        user_id = create_resp.json()["data"]["id"]

        deactivate_resp = api_client.post(
            f"/api/v1/users/{user_id}/deactivate", headers=auth_headers
        )
        assert deactivate_resp.status_code == 200
        assert deactivate_resp.json()["data"]["is_active"] is False

        # Soft-deleted, so a normal GET now 404s.
        get_resp = api_client.get(f"/api/v1/users/{user_id}", headers=auth_headers)
        assert get_resp.status_code == 404

        restore_resp = api_client.post(
            f"/api/v1/users/{user_id}/restore", headers=auth_headers
        )
        assert restore_resp.status_code == 200

        get_after_restore = api_client.get(f"/api/v1/users/{user_id}", headers=auth_headers)
        assert get_after_restore.status_code == 200

    def test_deactivating_the_last_owner_is_rejected(self, api_client, auth_headers, seeded_session):
        """Seed data has two owners (DEV_ADMIN_ID and OWNER_ID) — first
        deactivate one (should succeed, one owner remains), then attempt
        to deactivate the other (should be blocked at 409: it would leave
        the company with zero owners/admins)."""
        from database.seed.sample_data import OWNER_ID

        first = api_client.post(
            f"/api/v1/users/{OWNER_ID}/deactivate", headers=auth_headers
        )
        assert first.status_code == 200

        # dev-admin (the actor, still authenticated) is now the LAST
        # owner/admin — deactivating themselves would orphan the company.
        # deactivate_user() has no self-protection of its own (unlike
        # assign_role()'s self-role-change block), so this exercises the
        # last-admin guard specifically, not a self-action block.
        from database.seed.sample_data import DEV_ADMIN_ID

        second = api_client.post(
            f"/api/v1/users/{DEV_ADMIN_ID}/deactivate", headers=auth_headers
        )
        assert second.status_code == 409

    def test_deactivating_a_second_owner_succeeds(self, api_client, auth_headers, seeded_session):
        """Sanity check: the last-admin guard only fires when it's truly
        the last one — adding a second owner first must unblock it."""
        create_resp = api_client.post(
            "/api/v1/users",
            json={
                "email": "second-owner@example.com", "password": "SecurePass123!",
                "first_name": "Second", "last_name": "Owner", "role": "owner",
            },
            headers=auth_headers,
        )
        second_owner_id = create_resp.json()["data"]["id"]

        response = api_client.post(
            f"/api/v1/users/{second_owner_id}/deactivate", headers=auth_headers
        )
        assert response.status_code == 200


class TestRoleAssignment:
    def test_owner_can_promote_a_foreman(self, api_client, auth_headers):
        create_resp = api_client.post(
            "/api/v1/users",
            json={
                "email": "promoteme@example.com", "password": "SecurePass123!",
                "first_name": "Promote", "last_name": "Me", "role": "foreman",
            },
            headers=auth_headers,
        )
        target_id = create_resp.json()["data"]["id"]

        response = api_client.patch(
            f"/api/v1/users/{target_id}/role",
            json={"role": "project_manager"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["role"] == "project_manager"

    def test_cannot_assign_own_role(self, api_client, auth_headers, seeded_session):
        """Explicit requirement: a user can never change their own role,
        even as owner with USER_ASSIGN_ROLE."""
        from database.seed.sample_data import DEV_ADMIN_ID

        response = api_client.patch(
            f"/api/v1/users/{DEV_ADMIN_ID}/role",
            json={"role": "admin"},
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_project_manager_cannot_assign_admin_role(self, api_client, seeded_session, test_settings):
        """Role hierarchy: project_manager (rank 60) cannot assign admin
        (rank 80) — even though project_manager might theoretically hold
        USER_ASSIGN_ROLE in some future permission tweak, the hierarchy
        check is independent of the permission check. Today
        project_manager does NOT have USER_ASSIGN_ROLE at all, so this
        should 403 at the permission layer before ever reaching the
        hierarchy check — this test confirms the end-to-end block either way."""
        pm_user, pm_token = _make_user_and_token(
            seeded_session, test_settings, company_id=COMPANY_ID, role="project_manager",
            email="pm-noassign@example.com",
        )
        target_user, _target_token = _make_user_and_token(
            seeded_session, test_settings, company_id=COMPANY_ID, role="foreman",
            email="pm-target@example.com",
        )
        response = api_client.patch(
            f"/api/v1/users/{target_user.id}/role",
            json={"role": "admin"},
            headers={"Authorization": f"Bearer {pm_token}"},
        )
        assert response.status_code == 403

    def test_owner_cannot_assign_system_admin(self, api_client, auth_headers, seeded_session):
        """Role hierarchy: owner (rank 80) cannot assign system_admin
        (rank 100) — 'Company Admins cannot create System Admins.'"""
        create_resp = api_client.post(
            "/api/v1/users",
            json={
                "email": "wouldbe-sysadmin@example.com", "password": "SecurePass123!",
                "first_name": "Would", "last_name": "BeSysAdmin", "role": "foreman",
            },
            headers=auth_headers,
        )
        target_id = create_resp.json()["data"]["id"]

        response = api_client.patch(
            f"/api/v1/users/{target_id}/role",
            json={"role": "system_admin"},
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_demoting_the_last_owner_is_rejected(self, api_client, seeded_session):
        """Last-admin protection applies to role demotion too, not just
        deactivation. Seed data has two owners (DEV_ADMIN_ID, OWNER_ID) —
        demote one first (fine, one remains), then demoting the other
        (now the last owner/admin) must be blocked (409). Verified
        directly at the service layer (UserService.assign_role()) since
        this is a business-rule check independent of the HTTP/permission
        layers already covered by the other role-assignment tests."""
        import pytest
        from fastapi import HTTPException

        from app.services.user_service import UserService
        from database.seed.sample_data import DEV_ADMIN_ID, OWNER_ID
        from database.repositories.company import UserRepository

        user_repo = UserRepository(seeded_session)
        service = UserService(seeded_session)
        actor_id = uuid.uuid4()  # a different actor — not self-assignment

        owner_row = user_repo.get_by_id(OWNER_ID)
        service.assign_role(
            target_user=owner_row, new_role="foreman",
            actor_id=actor_id, actor_role="owner",
        )  # succeeds — dev-admin remains as owner

        dev_admin_row = user_repo.get_by_id(DEV_ADMIN_ID)
        with pytest.raises(HTTPException) as exc_info:
            service.assign_role(
                target_user=dev_admin_row, new_role="foreman",
                actor_id=actor_id, actor_role="owner",
            )
        assert exc_info.value.status_code == 409

    def test_demoting_one_of_two_owners_succeeds(self, api_client, auth_headers):
        """Sanity check: the guard only fires when it's truly the last
        one — adding a second owner first must unblock the demotion."""
        create_resp = api_client.post(
            "/api/v1/users",
            json={
                "email": "second-owner-demote@example.com", "password": "SecurePass123!",
                "first_name": "Second", "last_name": "Owner", "role": "owner",
            },
            headers=auth_headers,
        )
        target_id = create_resp.json()["data"]["id"]

        response = api_client.patch(
            f"/api/v1/users/{target_id}/role",
            json={"role": "foreman"},
            headers=auth_headers,
        )
        assert response.status_code == 200


class TestUserManagementCrossTenant:
    def test_cannot_get_user_from_another_company(self, api_client, seeded_session, test_settings):
        from database.models.company import Company

        company_b = Company(name="User Mgmt Company B", slug="user-mgmt-company-b")
        seeded_session.add(company_b)
        seeded_session.flush()
        user_b, _token_b = _make_user_and_token(
            seeded_session, test_settings, company_id=company_b.id, role="owner",
            email="companyb-owner@example.com",
        )
        seeded_session.commit()

        _actor, actor_token = _make_user_and_token(
            seeded_session, test_settings, company_id=COMPANY_ID, role="owner",
            email="companya-actor@example.com",
        )
        response = api_client.get(
            f"/api/v1/users/{user_b.id}",
            headers={"Authorization": f"Bearer {actor_token}"},
        )
        assert response.status_code == 404
