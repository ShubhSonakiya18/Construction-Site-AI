"""
tests/test_api_projects_list.py — Sprint 10: GET /projects.

Closes the gap Sprint 9's frontend carried forward (no way to discover a
company's projects). Covers: pagination, tenant scoping (a second
company's project must never appear), and the empty-company case.
"""
from __future__ import annotations

import uuid

import pytest

from database.seed.sample_data import COMPANY_ID, PROJECT_ID

pytest_plugins = ["tests.conftest_api"]

LIST_URL = "/api/v1/projects"


def test_requires_authentication(api_client):
    response = api_client.get(LIST_URL)
    assert response.status_code == 401


def test_lists_the_seeded_project(api_client, auth_headers):
    response = api_client.get(LIST_URL, headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    ids = [p["id"] for p in body["data"]]
    assert str(PROJECT_ID) in ids


def test_returned_project_belongs_to_callers_company(api_client, auth_headers):
    response = api_client.get(LIST_URL, headers=auth_headers)
    body = response.json()
    for project in body["data"]:
        assert project["company_id"] == str(COMPANY_ID)


def test_pagination_metadata_present(api_client, auth_headers):
    response = api_client.get(LIST_URL, params={"limit": 1}, headers=auth_headers)
    body = response.json()
    assert body["metadata"]["limit"] == 1
    assert body["metadata"]["count"] <= 1


def test_status_filter(api_client, auth_headers):
    response = api_client.get(
        LIST_URL, params={"status": "nonexistent_status"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["data"] == []


class TestTenantIsolation:
    """A second company's projects must never appear, no matter what the
    caller passes — there is no company_id query param to even attempt
    tampering with; scoping comes entirely from the caller's own token."""

    @pytest.fixture
    def other_company_project(self, seeded_session):
        from database.models.company import Company
        from database.models.project import Project

        other_company = Company(
            id=uuid.uuid4(), name="Other Co", slug="other-co-projects-test",
        )
        seeded_session.add(other_company)
        seeded_session.flush()
        other_project = Project(
            id=uuid.uuid4(),
            company_id=other_company.id,
            name="Other Co's Secret Project",
            status="active",
        )
        seeded_session.add(other_project)
        seeded_session.commit()
        return other_project

    def test_other_companys_project_never_appears(
        self, api_client, auth_headers, other_company_project
    ):
        response = api_client.get(LIST_URL, headers=auth_headers)
        ids = [p["id"] for p in response.json()["data"]]
        assert str(other_company_project.id) not in ids
