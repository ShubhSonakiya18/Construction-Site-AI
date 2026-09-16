"""
tests/test_prompt_builder.py — extraction/prompts/builder.py.

Sprint 14, Deliverable 1: the extraction prompt's schema reference had
drifted out of sync with knowledge/construction_daily_log_schema.json --
financials was missing entirely, and client_communication asked for a
narrower, differently-named shape than the schema actually defines. These
tests lock in that the prompt text now matches the schema for both
sections, so a future edit can't silently reintroduce the same drift.
"""
from __future__ import annotations

from extraction.prompts.builder import PromptBuilder


def _builder() -> PromptBuilder:
    return PromptBuilder(
        stage_enum=["site_preparation", "foundation", "framing"],
        weather_enum=["sunny", "cloudy"],
        trade_enum=["framing_carpenter", "electrician"],
    )


class TestFinancialsSection:
    def test_financials_block_present(self):
        prompt = _builder().build_prompt("Some transcript.")
        assert '"financials"' in prompt

    def test_financials_fields_match_the_real_schema(self):
        """knowledge/construction_daily_log_schema.json defines 8
        financials properties; the 3 running-total/derived ones
        (daily_total_cost_usd, cumulative_spend_to_date_usd,
        budget_remaining_usd) are deliberately NOT asked of the LLM --
        a single transcript can't know a running total, and the app
        computes the daily total server-side rather than trusting the
        LLM's own arithmetic (docs/NEXT_SPRINT.md, Deliverable 1)."""
        prompt = _builder().build_prompt("Some transcript.")
        for field in [
            "daily_labor_cost_usd",
            "daily_material_cost_usd",
            "daily_equipment_cost_usd",
            "daily_subcontractor_cost_usd",
            "financial_notes",
        ]:
            assert field in prompt, f"missing {field}"
        for derived_field in [
            "daily_total_cost_usd",
            "cumulative_spend_to_date_usd",
            "budget_remaining_usd",
        ]:
            assert derived_field not in prompt, (
                f"{derived_field} should be server-computed, not asked of the LLM"
            )


class TestClientCommunicationSection:
    """The prompt's client_communication block previously used field
    names (contact_made, customer_concerns, change_orders_discussed)
    that don't match knowledge/construction_daily_log_schema.json's
    real field names (client_contacted_today, client_concerns,
    change_orders) -- fixed alongside the financials gap since both
    are the same class of drift."""

    def test_uses_real_schema_field_names(self):
        prompt = _builder().build_prompt("Some transcript.")
        assert "client_contacted_today" in prompt
        assert "client_concerns" in prompt
        assert "communication_notes" in prompt
        # Stale field names must not reappear.
        assert "contact_made" not in prompt
        assert "customer_concerns" not in prompt
        assert "change_orders_discussed" not in prompt

    def test_change_orders_array_has_full_shape(self):
        prompt = _builder().build_prompt("Some transcript.")
        assert '"change_orders"' in prompt
        assert "change_order_id" in prompt
        assert "estimated_cost_impact_usd" in prompt
        assert "estimated_schedule_impact_days" in prompt
        for status in ["pending_approval", "approved", "rejected", "under_negotiation"]:
            assert status in prompt

    def test_contact_method_enum_matches_schema(self):
        prompt = _builder().build_prompt("Some transcript.")
        for method in [
            "phone_call", "email", "text_sms", "in_person_visit", "video_call", "client_portal",
        ]:
            assert method in prompt


class TestLanguageHandling:
    """Sprint 16, Deliverable 1 (ADR-064): extraction translates to
    English during extraction rather than switching Whisper's task to
    "translate" -- verified live with a real Spanish audio sample
    (see docs/DECISIONS.md) that this exact system-prompt rule turns
    fully-Spanish free-text fields into fully-English output with no
    other pipeline change."""

    def test_system_prompt_instructs_english_output_regardless_of_input_language(self):
        prompt = _builder().system_prompt
        assert "english" in prompt.lower()
        assert "any language" in prompt.lower()


class TestSafetySection:
    """Pre-Sprint-15 bug fix: `incidents` was a bare `[]` (no object
    shape at all -- confirmed live that a transcript describing a real
    injury produced an empty incidents array) and `hazards_identified`
    asked for plain strings while
    DailyLogRepository.create_from_extraction_result() calls .get() on
    each item expecting a dict -- confirmed live that this crashed
    create_from_extraction_result() with AttributeError on ANY real
    voice log mentioning a hazard, not just losing the hazard data.
    Field names had also drifted: the prompt asked for
    safety_meeting_held/safety_meeting_topic/ppe_compliance_percent
    while persistence (database/repositories/daily_log.py) already
    correctly read the real schema names
    (safety_meeting_conducted/safety_meeting_topics/
    ppe_compliance_observed) -- a second, independent form of the same
    drift Sprint 14 fixed for financials/client_communication."""

    def test_uses_real_schema_field_names(self):
        prompt = _builder().build_prompt("Some transcript.")
        assert "safety_meeting_conducted" in prompt
        assert "safety_meeting_topics" in prompt
        assert "ppe_compliance_observed" in prompt
        assert "ppe_required_today" in prompt
        # Stale field names that don't match the persistence layer must
        # not reappear.
        assert "safety_meeting_held" not in prompt
        assert "safety_meeting_topic\"" not in prompt
        assert "ppe_compliance_percent" not in prompt

    def test_incidents_array_has_full_object_shape(self):
        """Was a bare `[]` -- the LLM had no shape to extract into, so
        real incidents (verified live) were silently never captured."""
        prompt = _builder().build_prompt("Some transcript.")
        assert '"incidents": [' in prompt
        assert "incident_type" in prompt
        assert "osha_recordable" in prompt
        assert "medical_treatment_required" in prompt
        assert "incident_reported_to" in prompt
        for incident_type in [
            "first_aid", "medical_treatment", "lost_time_injury",
            "near_miss", "property_damage", "environmental", "equipment_damage",
        ]:
            assert incident_type in prompt

    def test_hazards_identified_has_full_object_shape_not_bare_strings(self):
        """Was `[<string>]` -- create_from_extraction_result() calls
        item.get('hazard_type') on each element, which raises
        AttributeError on a plain string. Confirmed live: this crashed
        the ENTIRE log save, not just hazard persistence."""
        prompt = _builder().build_prompt("Some transcript.")
        assert "hazard_type" in prompt
        assert "corrective_action" in prompt
        assert "corrective_action_completed" in prompt
        for hazard_type in [
            "fall_risk", "struck_by", "electrical_hazard", "trip_hazard",
        ]:
            assert hazard_type in prompt
        for severity in ["low", "medium", "high", "critical"]:
            assert severity in prompt
