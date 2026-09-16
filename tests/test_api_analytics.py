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
from database.models.log_items import LogDelay, LogWorkItem
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


class TestDelayFrequencyByTrade:
    """Sprint 13, Deliverable 2 (ADR-053): delay_frequency_by_trade credits
    every LogTradeOnSite row present on a log with every LogDelay recorded
    on that same log -- a broad "on site that day" join, not an attempt to
    infer which specific trade's work was blocked."""

    def test_no_delays_yields_empty_list(self, api_client, auth_headers):
        response = api_client.get(ANALYTICS_URL, headers=auth_headers)
        assert response.json()["data"]["delay_frequency_by_trade"] == []

    def test_credits_every_trade_on_site_with_every_delay_that_day(
        self, api_client, auth_headers, seeded_session
    ):
        from database.models.log_items import LogTradeOnSite

        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 6, 1), current_stage="framing",
            review_status="approved", total_workers_present=8,
        )
        seeded_session.add(log)
        seeded_session.flush()

        seeded_session.add_all([
            LogTradeOnSite(daily_log_id=log.id, trade="electrical", workers_count=2),
            LogTradeOnSite(daily_log_id=log.id, trade="plumbing", workers_count=3),
            LogDelay(
                daily_log_id=log.id, delay_type="material_shortage",
                description="Conduit delayed", hours_lost=4.0,
            ),
            LogDelay(
                daily_log_id=log.id, delay_type="weather",
                description="Rain", hours_lost=2.0,
            ),
        ])
        seeded_session.commit()

        response = api_client.get(ANALYTICS_URL, headers=auth_headers)
        by_trade = {e["trade"]: e for e in response.json()["data"]["delay_frequency_by_trade"]}

        # Both trades were on site the day both delays happened -- each
        # trade is credited with both delays (broad join, ADR-053), not
        # narrowed to whichever trade's work was actually blocked.
        assert by_trade["electrical"]["delay_count"] == 2
        assert by_trade["electrical"]["total_hours_lost"] == 6.0
        assert by_trade["plumbing"]["delay_count"] == 2
        assert by_trade["plumbing"]["total_hours_lost"] == 6.0

    def test_trade_not_on_a_delay_day_is_not_credited(
        self, api_client, auth_headers, seeded_session
    ):
        """A trade present on a delay-free log must not appear at all --
        only trades sharing a daily_log_id with an actual LogDelay row
        are aggregated."""
        from database.models.log_items import LogTradeOnSite

        clean_log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 6, 2), current_stage="framing",
            review_status="approved", total_workers_present=4,
        )
        seeded_session.add(clean_log)
        seeded_session.flush()
        seeded_session.add(
            LogTradeOnSite(daily_log_id=clean_log.id, trade="hvac", workers_count=2)
        )
        seeded_session.commit()

        response = api_client.get(ANALYTICS_URL, headers=auth_headers)
        trades = {e["trade"] for e in response.json()["data"]["delay_frequency_by_trade"]}
        assert "hvac" not in trades


class TestSafetyIncidentTrends:
    """Sprint 13, Deliverable 3: safety_incident_trend (time view) and
    safety_incident_breakdown (category view) over the same
    LogSafetyIncident rows, approved logs only."""

    @pytest.fixture
    def approved_log_with_incidents(self, seeded_session):
        """One approved log with three incidents: one explicitly
        OSHA-recordable, one explicitly not, one never assessed
        (osha_recordable=None) -- enough to assert the nullable
        column's handling."""
        from database.models.log_items import LogSafetyIncident

        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 7, 1), current_stage="framing",
            review_status="approved", total_workers_present=6,
        )
        seeded_session.add(log)
        seeded_session.flush()

        seeded_session.add_all([
            LogSafetyIncident(
                daily_log_id=log.id, incident_type="first_aid",
                description="Minor cut", osha_recordable=True,
            ),
            LogSafetyIncident(
                daily_log_id=log.id, incident_type="near_miss",
                description="Dropped tool", osha_recordable=False,
            ),
            LogSafetyIncident(
                daily_log_id=log.id, incident_type="near_miss",
                description="Trip hazard", osha_recordable=None,
            ),
        ])
        seeded_session.commit()
        return log

    def test_no_incidents_yields_empty_series(self, api_client, auth_headers):
        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        assert body["safety_incident_trend"] == []
        assert body["safety_incident_breakdown"] == []

    def test_trend_counts_incidents_per_day(
        self, api_client, auth_headers, approved_log_with_incidents
    ):
        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        by_date = {p["log_date"]: p for p in body["safety_incident_trend"]}

        assert by_date["2026-07-01"]["incident_count"] == 3
        # Only the explicitly-True incident counts as recordable: an
        # unassessed (NULL) one is not the same claim as "assessed and
        # not recordable", so it must not be counted here.
        assert by_date["2026-07-01"]["osha_recordable_count"] == 1

    def test_breakdown_groups_by_incident_type(
        self, api_client, auth_headers, approved_log_with_incidents
    ):
        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        by_type = {e["incident_type"]: e for e in body["safety_incident_breakdown"]}

        assert by_type["near_miss"]["incident_count"] == 2
        assert by_type["near_miss"]["osha_recordable_count"] == 0
        assert by_type["first_aid"]["incident_count"] == 1
        assert by_type["first_aid"]["osha_recordable_count"] == 1

    def test_breakdown_sorted_by_incident_count_descending(
        self, api_client, auth_headers, approved_log_with_incidents
    ):
        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        counts = [e["incident_count"] for e in body["safety_incident_breakdown"]]
        assert counts == sorted(counts, reverse=True)

    def test_draft_log_incidents_excluded(self, api_client, auth_headers, seeded_session):
        """Same approved-only trust boundary every other series applies."""
        from database.models.log_items import LogSafetyIncident

        draft = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 7, 2), current_stage="framing",
            review_status="draft", total_workers_present=5,
        )
        seeded_session.add(draft)
        seeded_session.flush()
        seeded_session.add(LogSafetyIncident(
            daily_log_id=draft.id, incident_type="lost_time_injury",
            description="Unreviewed", osha_recordable=True,
        ))
        seeded_session.commit()

        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        assert "lost_time_injury" not in {
            e["incident_type"] for e in body["safety_incident_breakdown"]
        }
        assert "2026-07-02" not in {p["log_date"] for p in body["safety_incident_trend"]}


class TestSafetyProactiveWarnings:
    """Sprint 15, Deliverable 4 (ADR-063): safety_proactive_warnings on
    the analytics response -- unresolved hazards, days since last
    incident, and an OSHA incidence rate, all computed at read time."""

    def test_no_hazards_or_incidents_yields_empty_warnings(self, api_client, auth_headers):
        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        warnings = body["safety_proactive_warnings"]
        assert warnings["unresolved_hazards"] == []
        assert warnings["days_since_last_incident"] is None

    def test_unresolved_hazard_appears_with_computed_days_open(
        self, api_client, auth_headers, seeded_session
    ):
        from database.models.log_items import LogHazard

        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 8, 1), current_stage="framing",
            review_status="approved", total_workers_present=5,
        )
        seeded_session.add(log)
        seeded_session.flush()
        seeded_session.add(LogHazard(
            daily_log_id=log.id, hazard_type="trip_hazard",
            description="Loose cabling", severity="medium",
            corrective_action_completed=False,
        ))
        seeded_session.commit()

        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        hazards = body["safety_proactive_warnings"]["unresolved_hazards"]
        assert len(hazards) == 1
        assert hazards[0]["hazard_type"] == "trip_hazard"
        assert hazards[0]["days_open"] >= 0

    def test_resolved_hazard_is_excluded(self, api_client, auth_headers, seeded_session):
        from database.models.log_items import LogHazard

        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 8, 2), current_stage="framing",
            review_status="approved", total_workers_present=5,
        )
        seeded_session.add(log)
        seeded_session.flush()
        seeded_session.add(LogHazard(
            daily_log_id=log.id, hazard_type="trip_hazard",
            description="Already fixed", severity="low",
            corrective_action_completed=True,
        ))
        seeded_session.commit()

        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        hazards = body["safety_proactive_warnings"]["unresolved_hazards"]
        assert "Already fixed" not in {h["description"] for h in hazards}

    def test_days_since_last_incident_reflects_the_most_recent_one(
        self, api_client, auth_headers, seeded_session
    ):
        from database.models.log_items import LogSafetyIncident

        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 8, 10), current_stage="framing",
            review_status="approved", total_workers_present=5,
        )
        seeded_session.add(log)
        seeded_session.flush()
        seeded_session.add(LogSafetyIncident(
            daily_log_id=log.id, incident_type="near_miss",
            description="Some incident", osha_recordable=False,
        ))
        seeded_session.commit()

        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        assert body["safety_proactive_warnings"]["days_since_last_incident"] is not None

    def test_incidence_rate_unavailable_with_insufficient_hours(
        self, api_client, auth_headers
    ):
        """The seeded sample project's total logged hours are well
        under the reliability floor -- must show a reason, not a
        misleadingly precise number."""
        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        warnings = body["safety_proactive_warnings"]
        assert warnings["incidence_rate_per_200k_hours"] is None
        assert warnings["incidence_rate_unavailable_reason"] is not None


class TestProductivityByStageAndTrade:
    """Sprint 13, Deliverable 4 (ADR-055): productivity_by_stage_trade
    averages LogWorkItem.task_completion_percent per (current_stage,
    trade), approved logs only, excluding items with no recorded
    percent."""

    def test_seeded_work_items_produce_an_averaged_entry(self, api_client, auth_headers):
        """The sample log has three framing_carpenter work items on the
        framing stage with completion percents 100, 100, 35 -- average
        (100+100+35)/3 = 78.33..., count 3."""
        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        entries = {
            (e["current_stage"], e["trade"]): e
            for e in body["productivity_by_stage_trade"]
        }
        entry = entries[("framing", "framing_carpenter")]
        assert entry["work_item_count"] == 3
        assert abs(entry["avg_task_completion_percent"] - 78.33) < 0.1

    def test_work_item_with_no_completion_percent_excluded_from_average(
        self, api_client, auth_headers, seeded_session
    ):
        """A NULL task_completion_percent means 'not reported', not
        '0% complete' -- it must not drag the average down or be
        counted in work_item_count."""
        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 7, 15), current_stage="drywall",
            review_status="approved", total_workers_present=4,
        )
        seeded_session.add(log)
        seeded_session.flush()
        seeded_session.add_all([
            LogWorkItem(
                daily_log_id=log.id, task_description="Hung drywall in kitchen",
                trade="drywall_installer", task_completion_percent=80.0,
            ),
            LogWorkItem(
                daily_log_id=log.id, task_description="Began taping (percent not yet reported)",
                trade="drywall_installer", task_completion_percent=None,
            ),
        ])
        seeded_session.commit()

        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        entries = {
            (e["current_stage"], e["trade"]): e
            for e in body["productivity_by_stage_trade"]
        }
        entry = entries[("drywall", "drywall_installer")]
        assert entry["work_item_count"] == 1
        assert entry["avg_task_completion_percent"] == 80.0

    def test_draft_log_work_items_excluded(self, api_client, auth_headers, seeded_session):
        draft = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 7, 16), current_stage="roofing",
            review_status="draft", total_workers_present=3,
        )
        seeded_session.add(draft)
        seeded_session.flush()
        seeded_session.add(LogWorkItem(
            daily_log_id=draft.id, task_description="Unreviewed roofing work",
            trade="roofer", task_completion_percent=50.0,
        ))
        seeded_session.commit()

        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        pairs = {(e["current_stage"], e["trade"]) for e in body["productivity_by_stage_trade"]}
        assert ("roofing", "roofer") not in pairs


class TestCostAnalytics:
    """Sprint 14, Deliverables 1/2/4: daily_cost_trend, budget_variance,
    and change_order_summary on the analytics response."""

    @pytest.fixture
    def approved_logs_with_costs(self, seeded_session):
        """Two approved logs carrying real financials objects, matching
        the shape ADR-058's extraction prompt produces (the four
        component fields only -- no derived totals)."""
        logs = []
        for log_date, financials in [
            (date(2026, 8, 1), {
                "daily_labor_cost_usd": 2000,
                "daily_material_cost_usd": 500,
            }),
            (date(2026, 8, 2), {
                "daily_labor_cost_usd": 1800,
                "daily_equipment_cost_usd": 200,
                "daily_subcontractor_cost_usd": 1000,
            }),
        ]:
            log = DailyLog(
                id=uuid.uuid4(), project_id=PROJECT_ID,
                log_date=log_date, current_stage="framing",
                review_status="approved", total_workers_present=5,
                financials=financials,
            )
            seeded_session.add(log)
            logs.append(log)
        seeded_session.commit()
        return logs

    # The seeded sample log (2026-05-14) already carries a real financials
    # object: 2887.50 labor + 1240.00 material + 150.00 equipment.
    SEEDED_LOG_TOTAL = 4277.50

    def test_seeded_log_appears_in_the_trend(self, api_client, auth_headers):
        """database/seed/sample_data.py's log is the one place financials
        was ever populated before Sprint 14 widened the extraction prompt
        -- it must show up with its components summed."""
        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        by_date = {p["log_date"]: p for p in body["daily_cost_trend"]}
        assert by_date["2026-05-14"]["daily_total_cost_usd"] == self.SEEDED_LOG_TOTAL

    def test_daily_and_cumulative_totals_are_computed_server_side(
        self, api_client, auth_headers, approved_logs_with_costs
    ):
        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        by_date = {p["log_date"]: p for p in body["daily_cost_trend"]}

        assert by_date["2026-08-01"]["daily_total_cost_usd"] == 2500.0
        assert by_date["2026-08-02"]["daily_total_cost_usd"] == 3000.0
        # Cumulative runs oldest-first across every approved log with
        # cost data, so it includes the seeded 2026-05-14 log ahead of
        # these two.
        assert by_date["2026-08-01"]["cumulative_spend_to_date_usd"] == (
            self.SEEDED_LOG_TOTAL + 2500.0
        )
        assert by_date["2026-08-02"]["cumulative_spend_to_date_usd"] == (
            self.SEEDED_LOG_TOTAL + 5500.0
        )
        # An unreported component stays null rather than becoming 0 --
        # "not reported" and "reported as zero" are different facts.
        assert by_date["2026-08-01"]["daily_equipment_cost_usd"] is None

    def test_budget_variance_compares_spend_against_contract_value(
        self, api_client, auth_headers, approved_logs_with_costs
    ):
        """The seeded project has contract_value_usd = 425000."""
        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        variance = body["budget_variance"]
        expected_spend = self.SEEDED_LOG_TOTAL + 5500.0

        assert variance["contract_value_usd"] == 425000.0
        assert variance["total_spend_to_date_usd"] == expected_spend
        assert variance["budget_remaining_usd"] == 425000.0 - expected_spend
        assert variance["status"] == "on_track"

    def test_over_budget_status_when_spend_exceeds_contract_value(
        self, api_client, auth_headers, seeded_session
    ):
        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 8, 20), current_stage="framing",
            review_status="approved", total_workers_present=5,
            financials={"daily_labor_cost_usd": 500_000},
        )
        seeded_session.add(log)
        seeded_session.commit()

        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        variance = body["budget_variance"]
        assert variance["status"] == "over_budget"
        assert variance["budget_remaining_usd"] < 0

    def test_material_cost_from_line_items_uses_real_recorded_data(
        self, api_client, auth_headers
    ):
        """Sprint 6's seeded LogMaterialUsed rows carry real unit costs --
        a second, more trustworthy source for material spend than the
        LLM's own estimate (ADR-058)."""
        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        assert body["budget_variance"]["material_cost_from_line_items_usd"] > 0

    def test_draft_log_costs_excluded(self, api_client, auth_headers, seeded_session):
        draft = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 8, 5), current_stage="framing",
            review_status="draft", total_workers_present=4,
            financials={"daily_labor_cost_usd": 99999},
        )
        seeded_session.add(draft)
        seeded_session.commit()

        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        assert "2026-08-05" not in {p["log_date"] for p in body["daily_cost_trend"]}

    def test_earned_value_computes_from_seeded_data(self, api_client, auth_headers):
        """The seeded project has a real contract value, a real approved
        log with a completion percent, and (once a schedule exists)
        real planned dates -- confirms the endpoint wires
        compute_earned_value() correctly against real fields, not just
        that the field is present."""
        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        evm = body["earned_value"]
        assert evm["actual_cost_usd"] == self.SEEDED_LOG_TOTAL
        # The seeded log reports overall_project_completion_percent=28,
        # contract_value_usd=425000 -> EV = 425000 * 0.28.
        assert evm["earned_value_usd"] == pytest.approx(425000.0 * 0.28)
        assert evm["cost_performance_index"] == pytest.approx(
            (425000.0 * 0.28) / self.SEEDED_LOG_TOTAL
        )
        # No schedule created in this test -> PV/SPI unavailable, but EV/
        # CPI still compute (EVM degrades per-field, not all-or-nothing).
        assert evm["planned_value_usd"] is None
        assert evm["schedule_performance_index"] is None

    def test_earned_value_uses_the_most_recent_reported_completion_percent(
        self, api_client, auth_headers, seeded_session
    ):
        """A later approved log that omits overall_project_completion_percent
        must not blank out EV -- the endpoint should fall back to the most
        recent log that actually reported one, not trend[-1] blindly.
        Regression test: found live against the real dev database, where
        two logs newer than the seeded one (both without a completion
        percent) were silently making earned_value_usd null even though
        the seeded log's real 28% was sitting right there."""
        newer_log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 9, 1), current_stage="framing",
            review_status="approved", total_workers_present=6,
            overall_project_completion_percent=None,
        )
        seeded_session.add(newer_log)
        seeded_session.commit()

        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        evm = body["earned_value"]
        # Still picks up the seeded log's 28%, not None from the newer log.
        assert evm["earned_value_usd"] == pytest.approx(425000.0 * 0.28)

    def test_earned_value_includes_planned_value_once_a_schedule_exists(
        self, api_client, auth_headers
    ):
        create = api_client.post(
            f"/api/v1/projects/{PROJECT_ID}/schedule", headers=auth_headers, json={},
        )
        assert create.status_code == 201

        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        evm = body["earned_value"]
        assert evm["planned_value_usd"] is not None
        assert 0.0 <= evm["planned_value_usd"] <= 425000.0

    def test_change_order_summary_groups_by_status(
        self, api_client, auth_headers, seeded_session
    ):
        from database.models.log_items import LogChangeOrder

        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 8, 10), current_stage="framing",
            review_status="approved", total_workers_present=5,
        )
        seeded_session.add(log)
        seeded_session.flush()
        seeded_session.add_all([
            LogChangeOrder(
                daily_log_id=log.id, description="Quartz countertop upgrade",
                estimated_cost_impact_usd=4200, status="approved",
            ),
            LogChangeOrder(
                daily_log_id=log.id, description="Recessed lighting",
                estimated_cost_impact_usd=1800, status="under_negotiation",
            ),
            LogChangeOrder(
                daily_log_id=log.id, description="Undecided scope change",
                estimated_cost_impact_usd=None, status="under_negotiation",
            ),
        ])
        seeded_session.commit()

        body = api_client.get(ANALYTICS_URL, headers=auth_headers).json()["data"]
        by_status = {e["status"]: e for e in body["change_order_summary"]}

        assert by_status["approved"]["change_order_count"] == 1
        assert by_status["approved"]["total_cost_impact_usd"] == 4200.0
        # A change order with no cost estimate still counts as a real
        # occurrence while contributing 0 to the total.
        assert by_status["under_negotiation"]["change_order_count"] == 2
        assert by_status["under_negotiation"]["total_cost_impact_usd"] == 1800.0


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
            financials={"daily_labor_cost_usd": 77777},
        )
        seeded_session.add(other_log)
        seeded_session.flush()
        seeded_session.add(LogDelay(
            daily_log_id=other_log.id, delay_type="labor_shortage",
            description="short crew", hours_lost=10.0,
        ))
        from database.models.log_items import (
            LogChangeOrder, LogHazard, LogSafetyIncident, LogTradeOnSite,
        )
        seeded_session.add_all([
            LogChangeOrder(
                daily_log_id=other_log.id, description="Other company's change order",
                estimated_cost_impact_usd=55555, status="approved",
            ),
            LogTradeOnSite(daily_log_id=other_log.id, trade="masonry", workers_count=2),
            LogSafetyIncident(
                daily_log_id=other_log.id, incident_type="lost_time_injury",
                description="Other company's incident", osha_recordable=True,
            ),
            LogHazard(
                daily_log_id=other_log.id, hazard_type="fall_risk",
                description="Other company's unresolved hazard", severity="critical",
                corrective_action_completed=False,
            ),
            LogWorkItem(
                daily_log_id=other_log.id, task_description="Other company's work",
                trade="masonry", task_completion_percent=90.0,
            ),
        ])
        seeded_session.commit()

        response = api_client.get(ANALYTICS_URL, headers=auth_headers)
        body = response.json()["data"]
        assert "labor_shortage" not in {e["delay_type"] for e in body["delay_frequency"]}
        assert "2026-05-20" not in {p["log_date"] for p in body["completion_trend"]}
        assert "masonry" not in {e["trade"] for e in body["delay_frequency_by_trade"]}
        assert "lost_time_injury" not in {
            e["incident_type"] for e in body["safety_incident_breakdown"]
        }
        assert body["safety_incident_trend"] == []
        assert "masonry" not in {
            e["trade"] for e in body["productivity_by_stage_trade"]
        }
        # The other company's $77,777 log and $55,555 change order must
        # not appear in this company's cost figures. (The seeded sample
        # log's own financials legitimately do -- same company.)
        assert "2026-05-20" not in {p["log_date"] for p in body["daily_cost_trend"]}
        assert body["change_order_summary"] == []
        assert body["budget_variance"]["total_spend_to_date_usd"] < 77_777
        assert body["earned_value"]["actual_cost_usd"] < 77_777
        assert "Other company's unresolved hazard" not in {
            h["description"] for h in body["safety_proactive_warnings"]["unresolved_hazards"]
        }
