"""
tests/test_osha_log_export.py — app/services/osha_log_export.py.

Sprint 15, Deliverable 3. Pure-function tests against small hand-built
OshaLogIncident fixtures, no database -- matching
tests/test_lead_time_warnings.py/test_cost_computation.py's approach for
their own session-free service modules. build_osha_300_log() itself
produces real PDF bytes; these tests check the structural
readiness/exclusion logic feeding it, which is what actually determines
correctness (a malformed PDF from correct inputs would be a reportlab
bug, not a logic bug this test file is positioned to catch -- see the
live-verification pass in docs/DECISIONS.md for the actual rendered
output check).
"""
from __future__ import annotations

from datetime import date

from app.services.osha_log_export import (
    OshaLogIncident,
    build_osha_300_log,
    classify_incident_readiness,
)


def _incident(**overrides) -> OshaLogIncident:
    defaults = dict(
        case_number="2026-001",
        log_date=date(2026, 8, 1),
        worker_name="James Thompson",
        job_title="foreman",
        description="Twisted ankle.",
        osha_classification="days_away_from_work",
        injury_illness_type="injury",
        days_away_from_work_count=3,
        days_of_job_transfer_or_restriction_count=None,
        is_review_ready=True,
        review_reason=None,
    )
    defaults.update(overrides)
    return OshaLogIncident(**defaults)


class TestClassifyIncidentReadiness:
    def test_ready_when_recordable_classified_and_worker_matched(self):
        ready, reason = classify_incident_readiness(
            osha_recordable=True, osha_classification="days_away_from_work",
            worker_id="some-uuid", worker_match_status="matched",
        )
        assert ready is True
        assert reason is None

    def test_not_ready_but_no_review_needed_when_explicitly_not_recordable(self):
        """osha_recordable=False is a real, already-made determination
        that this incident doesn't belong on the log -- excluded from
        the table, but reason=None means it must NOT be counted toward
        "needs review" (a safety officer who already decided this one
        doesn't need a second prompt)."""
        ready, reason = classify_incident_readiness(
            osha_recordable=False, osha_classification="days_away_from_work",
            worker_id="some-uuid", worker_match_status="matched",
        )
        assert ready is False
        assert reason is None

    def test_not_ready_and_needs_review_when_recordable_is_none(self):
        """Not yet assessed (NULL) is a real review-needed blocker --
        distinct from an explicit False -- same NULL-handling posture
        Sprint 13's osha_recordable_count already established."""
        ready, reason = classify_incident_readiness(
            osha_recordable=None, osha_classification="days_away_from_work",
            worker_id="some-uuid", worker_match_status="matched",
        )
        assert ready is False
        assert reason is not None

    def test_not_ready_when_classification_missing(self):
        ready, reason = classify_incident_readiness(
            osha_recordable=True, osha_classification=None,
            worker_id="some-uuid", worker_match_status="matched",
        )
        assert ready is False
        assert "classification" in reason

    def test_not_ready_when_worker_needs_review(self):
        ready, reason = classify_incident_readiness(
            osha_recordable=True, osha_classification="days_away_from_work",
            worker_id=None, worker_match_status="needs_review",
        )
        assert ready is False
        assert "worker" in reason.lower()

    def test_not_ready_when_no_worker_matched(self):
        ready, reason = classify_incident_readiness(
            osha_recordable=True, osha_classification="days_away_from_work",
            worker_id=None, worker_match_status="no_match",
        )
        assert ready is False

    def test_reason_reports_the_first_blocker_in_fixed_order(self):
        """Multiple things missing at once -- the reason given is
        deterministic (recordability checked first), not arbitrary."""
        ready, reason = classify_incident_readiness(
            osha_recordable=None, osha_classification=None,
            worker_id=None, worker_match_status="no_match",
        )
        assert "assessed" in reason.lower()


class TestBuildOsha300Log:
    def test_ready_incidents_are_included(self):
        result = build_osha_300_log(
            [_incident()], project_name="Test Project", calendar_year=2026,
        )
        assert result.included_count == 1
        assert result.excluded_needs_review == []
        assert len(result.pdf_bytes) > 0

    def test_not_ready_incidents_are_excluded_not_silently_dropped(self):
        not_ready = _incident(is_review_ready=False, review_reason="missing OSHA classification")
        result = build_osha_300_log(
            [not_ready], project_name="Test Project", calendar_year=2026,
        )
        assert result.included_count == 0
        assert len(result.excluded_needs_review) == 1
        assert result.excluded_needs_review[0].review_reason == "missing OSHA classification"
        # Still produces a real PDF (an explanatory one), not an empty byte string.
        assert len(result.pdf_bytes) > 0

    def test_explicitly_not_recordable_is_excluded_without_inflating_review_count(self):
        not_recordable = _incident(is_review_ready=False, review_reason=None)
        result = build_osha_300_log(
            [not_recordable], project_name="Test Project", calendar_year=2026,
        )
        assert result.included_count == 0
        assert result.excluded_needs_review == []

    def test_mixed_ready_and_not_ready(self):
        result = build_osha_300_log(
            [_incident(), _incident(is_review_ready=False, review_reason="no worker matched")],
            project_name="Test Project", calendar_year=2026,
        )
        assert result.included_count == 1
        assert len(result.excluded_needs_review) == 1

    def test_empty_incident_list_still_produces_a_pdf(self):
        result = build_osha_300_log([], project_name="Test Project", calendar_year=2026)
        assert result.included_count == 0
        assert result.excluded_needs_review == []
        assert len(result.pdf_bytes) > 0

    def test_unicode_in_description_does_not_crash_rendering(self):
        """The same Unicode-punctuation failure mode
        app/services/pdf_export.py's _sanitize_for_pdf_font fixes for
        Markdown documents applies identically to incident text --
        reused here rather than duplicated."""
        incident = _incident(description="Worker said “watch out—that beam” before it fell.")
        result = build_osha_300_log(
            [incident], project_name="Test Project", calendar_year=2026,
        )
        assert result.included_count == 1
        assert len(result.pdf_bytes) > 0

    def test_missing_case_number_renders_as_a_placeholder_not_a_crash(self):
        incident = _incident(case_number=None)
        result = build_osha_300_log(
            [incident], project_name="Test Project", calendar_year=2026,
        )
        assert result.included_count == 1

    def test_project_name_with_an_em_dash_does_not_crash_the_pdf_title(self):
        """Regression test: found live against the real database -- the
        seeded sample project's own name ("Johnson Residence — 123 Oak
        Street") crashed the whole request with a 'latin-1' codec error
        because build_osha_300_log()'s SimpleDocTemplate(title=...) used
        an unsanitized f-string containing a literal em-dash. HTTP
        headers and reportlab's PDF title metadata both require
        latin-1-safe text; _sanitize_for_pdf_font() (reused from
        pdf_export.py) fixes this the same way it already fixes body
        text, but the title= parameter itself was missed in the first
        pass -- this test pins that it's covered now."""
        result = build_osha_300_log(
            [_incident()], project_name="Johnson Residence — 123 Oak Street", calendar_year=2026,
        )
        assert result.included_count == 1
        assert len(result.pdf_bytes) > 0
