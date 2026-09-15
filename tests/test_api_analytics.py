"""
tests/test_api_analytics.py — Sprint 10: GET /projects/{id}/analytics.

Both series (completion trend, delay frequency) are computed from
approved logs only — the same trust boundary the grounded Q&A service
(ADR-042) applies. Seeds a small, controlled set of logs+delays directly
via the ORM so the aggregation math itself is asserted, not just "the
endpoint returns 200."
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from database.models.daily_log import DailyLog
from database.models.log_items import LogDelay
from database.seed.sample_data import DAILY_LOG_ID, PROJECT_ID

pytest_plugins = ["tests.conftest_api"]

ANALYTICS_URL = f"/api/v1/projects/{PROJECT_ID}/analytics"


def test_requires_authentication(api_client):
    response = api_client.get(ANALYTICS_URL)
    assert response.status_code == 401


def test_unknown_project_returns_404(api_client, auth_headers):
    response = api_client.get(f"/api/v1/projects/{uuid.uuid4()}/analytics", headers=auth_headers)
    assert response.status_code == 404


def test_seeded_project_has_a_completion_trend_point(api_client, auth_headers):
    """The seeded sample log is approved with a completion percent set —
    it must appear in the trend."""
    response = api_client.get(ANALYTICS_URL, headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["logs_analyzed"] >= 1
    dates = [p["log_date"] for p in body["completion_trend"]]
    assert "2026-05-14" in dates


class TestDelayAggregation:
    @pytest.fixture
    def extra_approved_log_with_delays(self, seeded_session):
        """A second approved log for the seeded project, with two
        material_shortage delays and one weather delay — enough to
        assert both occurrence_count and total_hours_lost math."""
        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 5, 15), current_stage="framing",
            review_status="approved", total_workers_present=6,
            overall_project_completion_percent=32.0,
        )
        seeded_session.add(log)
        seeded_session.flush()

        seeded_session.add_all([
            LogDelay(
                daily_log_id=log.id, delay_type="material_shortage",
                description="Studs delayed", hours_lost=2.5,
            ),
            LogDelay(
                daily_log_id=log.id, delay_type="material_shortage",
                description="OSB delayed", hours_lost=1.5,
            ),
            LogDelay(
                daily_log_id=log.id, delay_type="weather",
                description="Rain", hours_lost=None,  # duration unknown
            ),
        ])
        seeded_session.commit()
        return log

    def test_delay_frequency_counts_and_sums_hours_correctly(
        self, api_client, auth_headers, extra_approved_log_with_delays
    ):
        response = api_client.get(ANALYTICS_URL, headers=auth_headers)
        body = response.json()["data"]
        by_type = {e["delay_type"]: e for e in body["delay_frequency"]}

        assert by_type["material_shortage"]["occurrence_count"] == 2
        assert by_type["material_shortage"]["total_hours_lost"] == 4.0

        # A delay with hours_lost=None must still count as an occurrence
        # (it happened) while contributing 0, not being dropped entirely
        # or crashing the aggregation.
        assert by_type["weather"]["occurrence_count"] == 1
        assert by_type["weather"]["total_hours_lost"] == 0.0

    def test_sorted_by_occurrence_count_descending(
        self, api_client, auth_headers, extra_approved_log_with_delays
    ):
        response = api_client.get(ANALYTICS_URL, headers=auth_headers)
        counts = [e["occurrence_count"] for e in response.json()["data"]["delay_frequency"]]
        assert counts == sorted(counts, reverse=True)

    def test_second_approved_log_extends_the_completion_trend(
        self, api_client, auth_headers, extra_approved_log_with_delays
    ):
        response = api_client.get(ANALYTICS_URL, headers=auth_headers)
        body = response.json()["data"]
        assert body["logs_analyzed"] >= 2
        dates = [p["log_date"] for p in body["completion_trend"]]
        assert "2026-05-15" in dates

    def test_draft_log_does_not_appear_in_analytics(self, api_client, auth_headers, seeded_session):
        """An unreviewed log's self-reported completion percent has not
        been confirmed accurate — must not appear."""
        draft = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 5, 16), current_stage="framing",
            review_status="draft", total_workers_present=5,
            overall_project_completion_percent=99.0,
        )
        seeded_session.add(draft)
        seeded_session.commit()

        response = api_client.get(ANALYTICS_URL, headers=auth_headers)
        dates = [p["log_date"] for p in response.json()["data"]["completion_trend"]]
        assert "2026-05-16" not in dates


class TestProjectedCompletion:
    """Sprint 13, Deliverable 1 (ADR-052): GET /projects/{id}/analytics
    gains projected_completion_date/delay_adjusted_completion_date from
    Sprint 11's ProjectSchedule when one exists."""

    def test_no_schedule_yet_returns_null_for_both_fields(self, api_client, auth_headers):
        response = api_client.get(ANALYTICS_URL, headers=auth_headers)
        body = response.json()["data"]
        assert body["projected_completion_date"] is None
        assert body["delay_adjusted_completion_date"] is None

    def test_schedule_exists_returns_projected_completion_date(
        self, api_client, auth_headers
    ):
        create = api_client.post(
            f"/api/v1/projects/{PROJECT_ID}/schedule", headers=auth_headers, json={},
        )
        assert create.status_code == 201
        expected = create.json()["data"]["projected_completion_date"]

        response = api_client.get(ANALYTICS_URL, headers=auth_headers)
        body = response.json()["data"]
        assert body["projected_completion_date"] == expected

    def test_delay_adjusted_date_matches_schedule_endpoints_own_computation(
        self, api_client, auth_headers, seeded_session
    ):
        """Regression guard for ADR-052's whole reason for existing:
        the analytics endpoint must return the exact same
        delay_adjusted_completion_date the schedule endpoint itself
        computes -- both call the same factored-out helper, so a real
        critical-path-impacting delay must produce identical values in
        both places, not two independently-drifting computations."""
        from database.models.log_items import LogDelay

        create = api_client.post(
            f"/api/v1/projects/{PROJECT_ID}/schedule", headers=auth_headers, json={},
        )
        assert create.status_code == 201

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

        schedule_response = api_client.get(
            f"/api/v1/projects/{PROJECT_ID}/schedule", headers=auth_headers,
        )
        analytics_response = api_client.get(ANALYTICS_URL, headers=auth_headers)

        schedule_adjusted = schedule_response.json()["data"]["delay_adjusted_completion_date"]
        analytics_adjusted = analytics_response.json()["data"]["delay_adjusted_completion_date"]
        assert schedule_adjusted == analytics_adjusted
        assert analytics_adjusted != analytics_response.json()["data"]["projected_completion_date"]


class TestTenantIsolation:
    def test_other_companys_delays_never_counted(self, api_client, auth_headers, seeded_session):
        from database.models.company import Company
        from database.models.project import Project

        other_company = Company(id=uuid.uuid4(), name="Other Co", slug="other-co-analytics-test")
        seeded_session.add(other_company)
        seeded_session.flush()
        other_project = Project(
            id=uuid.uuid4(), company_id=other_company.id, name="Other Project", status="active",
        )
        seeded_session.add(other_project)
        seeded_session.flush()
        other_log = DailyLog(
            id=uuid.uuid4(), project_id=other_project.id,
            log_date=date(2026, 5, 20), current_stage="framing",
            review_status="approved", total_workers_present=3,
        )
        seeded_session.add(other_log)
        seeded_session.flush()
        seeded_session.add(LogDelay(
            daily_log_id=other_log.id, delay_type="labor_shortage",
            description="short crew", hours_lost=10.0,
        ))
        seeded_session.commit()

        response = api_client.get(ANALYTICS_URL, headers=auth_headers)
        body = response.json()["data"]
        assert "labor_shortage" not in {e["delay_type"] for e in body["delay_frequency"]}
        assert "2026-05-20" not in {p["log_date"] for p in body["completion_trend"]}
