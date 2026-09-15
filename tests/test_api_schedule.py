"""
tests/test_api_schedule.py — Sprint 11: POST/GET /projects/{id}/schedule,
and the Deliverable 4 actual-date-population hook on POST
/daily-logs/{id}/approve.

Same two-company tenant-isolation pattern every Sprint 10 API test file
uses (test_api_analytics.py, test_api_project_qa.py, ...).
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from database.models.company import Company
from database.models.daily_log import DailyLog
from database.models.log_items import LogDelay
from database.models.project import Project
from database.seed.sample_data import PROJECT_ID

pytest_plugins = ["tests.conftest_api"]

SCHEDULE_URL = f"/api/v1/projects/{PROJECT_ID}/schedule"


def test_get_requires_authentication(api_client):
    response = api_client.get(SCHEDULE_URL)
    assert response.status_code == 401


def test_post_requires_authentication(api_client):
    response = api_client.post(SCHEDULE_URL, json={})
    assert response.status_code == 401


def test_get_before_creation_is_404(api_client, auth_headers):
    response = api_client.get(SCHEDULE_URL, headers=auth_headers)
    assert response.status_code == 404


def test_get_unknown_project_is_404(api_client, auth_headers):
    response = api_client.get(
        f"/api/v1/projects/{uuid.uuid4()}/schedule", headers=auth_headers
    )
    assert response.status_code == 404


class TestCreateSchedule:
    def test_create_returns_201_with_23_tasks(self, api_client, auth_headers):
        response = api_client.post(SCHEDULE_URL, headers=auth_headers, json={})
        assert response.status_code == 201, response.text
        body = response.json()["data"]
        assert body["project_id"] == str(PROJECT_ID)
        assert len(body["tasks"]) == 23
        assert len(body["variance"]) == 23

    def test_created_schedule_uses_projects_start_date(self, api_client, auth_headers):
        response = api_client.post(SCHEDULE_URL, headers=auth_headers, json={})
        body = response.json()["data"]
        # Seeded project's project_start_date is 2026-03-10
        # (database/seed/sample_data.py) -- the first task's planned
        # start should match it exactly.
        assert body["schedule_start_date"] == "2026-03-10"

    def test_at_least_one_task_is_on_critical_path(self, api_client, auth_headers):
        response = api_client.post(SCHEDULE_URL, headers=auth_headers, json={})
        body = response.json()["data"]
        assert any(t["is_on_critical_path"] for t in body["tasks"])

    def test_critical_path_total_days_is_positive(self, api_client, auth_headers):
        response = api_client.post(SCHEDULE_URL, headers=auth_headers, json={})
        body = response.json()["data"]
        assert body["critical_path_total_days"] > 0
        assert body["projected_completion_date"] is not None

    def test_calling_create_twice_is_idempotent(self, api_client, auth_headers):
        first = api_client.post(SCHEDULE_URL, headers=auth_headers, json={})
        second = api_client.post(SCHEDULE_URL, headers=auth_headers, json={})
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["data"]["schedule_id"] == second.json()["data"]["schedule_id"]

    def test_explicit_start_date_overrides_project_default(self, api_client, auth_headers):
        response = api_client.post(
            SCHEDULE_URL, headers=auth_headers, json={"start_date": "2026-01-01"},
        )
        assert response.status_code == 201
        assert response.json()["data"]["schedule_start_date"] == "2026-01-01"

    def test_get_after_create_returns_the_same_schedule(self, api_client, auth_headers):
        created = api_client.post(SCHEDULE_URL, headers=auth_headers, json={})
        fetched = api_client.get(SCHEDULE_URL, headers=auth_headers)
        assert fetched.status_code == 200
        assert fetched.json()["data"]["schedule_id"] == created.json()["data"]["schedule_id"]


class TestTenantIsolation:
    def test_cannot_create_schedule_for_another_companys_project(
        self, api_client, auth_headers, seeded_session
    ):
        other_company = Company(id=uuid.uuid4(), name="Other Co", slug="other-co-schedule-test")
        seeded_session.add(other_company)
        seeded_session.flush()
        other_project = Project(
            id=uuid.uuid4(), company_id=other_company.id, name="Other Project",
            status="active", project_start_date=date(2026, 1, 1),
        )
        seeded_session.add(other_project)
        seeded_session.commit()

        response = api_client.post(
            f"/api/v1/projects/{other_project.id}/schedule", headers=auth_headers, json={},
        )
        assert response.status_code == 404

    def test_cannot_read_another_companys_schedule(
        self, api_client, auth_headers, seeded_session
    ):
        other_company = Company(id=uuid.uuid4(), name="Other Co 2", slug="other-co-schedule-test-2")
        seeded_session.add(other_company)
        seeded_session.flush()
        other_project = Project(
            id=uuid.uuid4(), company_id=other_company.id, name="Other Project 2",
            status="active", project_start_date=date(2026, 1, 1),
        )
        seeded_session.add(other_project)
        seeded_session.commit()

        response = api_client.get(
            f"/api/v1/projects/{other_project.id}/schedule", headers=auth_headers,
        )
        # 404 either way (no schedule exists yet, or cross-tenant) --
        # the point is it's never a 200 leaking another company's data.
        assert response.status_code == 404


class TestApprovalPopulatesActualDates:
    """Sprint 11 Deliverable 4: approving a log updates the matching
    schedule_tasks row's actual_start_date/actual_end_date."""

    @pytest.fixture
    def draft_log(self, seeded_session):
        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 4, 5), current_stage="foundation",
            review_status="under_review", total_workers_present=4,
            stage_completion_percent=None,
        )
        seeded_session.add(log)
        seeded_session.commit()
        return log

    def test_approving_a_log_sets_actual_start_date(
        self, api_client, auth_headers, draft_log, seeded_session
    ):
        # Schedule must exist first -- the approval hook is best-effort
        # and silently no-ops without one (see ScheduleRepository.
        # record_actual_progress()'s docstring).
        create = api_client.post(SCHEDULE_URL, headers=auth_headers, json={})
        assert create.status_code == 201

        response = api_client.post(
            f"/api/v1/daily-logs/{draft_log.id}/approve",
            headers=auth_headers, json={},
        )
        assert response.status_code == 200, response.text

        from database.models.schedule import ScheduleTask
        seeded_session.expire_all()
        task = (
            seeded_session.query(ScheduleTask)
            .filter(ScheduleTask.stage_id == "foundation")
            .one()
        )
        assert task.actual_start_date == date(2026, 4, 5)
        assert task.actual_end_date is None

    def test_approval_still_succeeds_with_no_schedule_yet(
        self, api_client, auth_headers, draft_log
    ):
        """The approval itself must never fail just because
        build_schedule_for_project() was never called for this
        project — the hook is best-effort, not a precondition."""
        response = api_client.post(
            f"/api/v1/daily-logs/{draft_log.id}/approve",
            headers=auth_headers, json={},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["review_status"] == "approved"

    @pytest.fixture
    def draft_log_completing_foundation(self, seeded_session):
        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 4, 20), current_stage="foundation",
            review_status="under_review", total_workers_present=4,
            stage_completion_percent=100.0,
        )
        seeded_session.add(log)
        seeded_session.commit()
        return log

    def test_100_percent_completion_sets_actual_end_date(
        self, api_client, auth_headers, draft_log_completing_foundation, seeded_session
    ):
        create = api_client.post(SCHEDULE_URL, headers=auth_headers, json={})
        assert create.status_code == 201

        response = api_client.post(
            f"/api/v1/daily-logs/{draft_log_completing_foundation.id}/approve",
            headers=auth_headers, json={},
        )
        assert response.status_code == 200

        from database.models.schedule import ScheduleTask
        seeded_session.expire_all()
        task = (
            seeded_session.query(ScheduleTask)
            .filter(ScheduleTask.stage_id == "foundation")
            .one()
        )
        assert task.actual_end_date == date(2026, 4, 20)


class TestDelayImpactPropagation:
    """Sprint 11 Deliverable 6: a critical_path_impacted delay on an
    approved log pushes delay_adjusted_completion_date forward, computed
    at read time (never persisted) — see ADR-048."""

    @pytest.fixture
    def approved_log_with_critical_delay(self, seeded_session):
        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 3, 20), current_stage="foundation",
            review_status="approved", total_workers_present=4,
        )
        seeded_session.add(log)
        seeded_session.flush()
        seeded_session.add(LogDelay(
            daily_log_id=log.id, delay_type="material_shortage",
            description="Rebar delivery delayed", hours_lost=48.0,
            schedule_impact="critical_path_impacted",
            days_lost_to_schedule=6.0,
        ))
        seeded_session.commit()
        return log

    def test_no_critical_delay_means_no_adjustment(self, api_client, auth_headers):
        create = api_client.post(SCHEDULE_URL, headers=auth_headers, json={})
        body = create.json()["data"]
        assert body["delay_impact_days"] == 0
        assert body["delay_adjusted_completion_date"] == body["projected_completion_date"]

    def test_critical_delay_pushes_completion_date_out(
        self, api_client, auth_headers, approved_log_with_critical_delay
    ):
        create = api_client.post(SCHEDULE_URL, headers=auth_headers, json={})
        assert create.status_code == 201

        response = api_client.get(SCHEDULE_URL, headers=auth_headers)
        body = response.json()["data"]
        assert body["delay_impact_days"] == 6
        assert body["delay_adjusted_completion_date"] != body["projected_completion_date"]

    def test_non_critical_delay_is_ignored(self, api_client, auth_headers, seeded_session):
        create = api_client.post(SCHEDULE_URL, headers=auth_headers, json={})
        assert create.status_code == 201

        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 3, 21), current_stage="foundation",
            review_status="approved", total_workers_present=4,
        )
        seeded_session.add(log)
        seeded_session.flush()
        seeded_session.add(LogDelay(
            daily_log_id=log.id, delay_type="weather",
            description="light rain", hours_lost=1.0,
            schedule_impact="minor_impact", days_lost_to_schedule=0.1,
        ))
        seeded_session.commit()

        response = api_client.get(SCHEDULE_URL, headers=auth_headers)
        body = response.json()["data"]
        assert body["delay_impact_days"] == 0
