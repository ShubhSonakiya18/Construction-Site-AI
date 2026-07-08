"""
tests/test_generation_models.py — Unit tests for Sprint 5 Pydantic output models.

Tests cover: ServiceType, ServiceMetadata, ServiceOutput (and typed subclasses),
GenerationResult, serialization, and factory classmethods.
No LLM calls, no file I/O.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from generation.models.outputs import (
    CustomerUpdate,
    DailyReport,
    GenerationResult,
    MaterialReminder,
    ServiceMetadata,
    ServiceOutput,
    ServiceType,
    ToolboxTalk,
)


# ── ServiceType ────────────────────────────────────────────────────────────────

class TestServiceType:
    def test_all_four_values_exist(self):
        assert ServiceType.DAILY_REPORT.value == "daily_report"
        assert ServiceType.CUSTOMER_UPDATE.value == "customer_update"
        assert ServiceType.SAFETY_TALK.value == "safety_talk"
        assert ServiceType.MATERIAL_REMINDER.value == "material_reminder"

    def test_is_string_enum(self):
        assert isinstance(ServiceType.DAILY_REPORT, str)
        assert ServiceType("daily_report") is ServiceType.DAILY_REPORT

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            ServiceType("nonexistent_service")


# ── ServiceMetadata ────────────────────────────────────────────────────────────

class TestServiceMetadata:
    def test_construction_with_required_fields(self):
        meta = ServiceMetadata(
            service_type=ServiceType.DAILY_REPORT,
            model="llama-3.3-70b-versatile",
            prompt_name="daily_report",
            prompt_version="1.0.0",
        )
        assert meta.service_type is ServiceType.DAILY_REPORT
        assert meta.model == "llama-3.3-70b-versatile"
        assert meta.prompt_version == "1.0.0"
        assert meta.provider == "groq"  # default
        assert meta.retry_count == 0
        assert meta.estimated_cost_usd == 0.0

    def test_generated_at_defaults_to_utc_now(self):
        before = datetime.now(timezone.utc)
        meta = ServiceMetadata(
            service_type=ServiceType.CUSTOMER_UPDATE,
            model="test-model",
            prompt_name="customer_update",
            prompt_version="1.0.0",
        )
        after = datetime.now(timezone.utc)
        assert before <= meta.generated_at <= after

    def test_all_token_fields(self):
        meta = ServiceMetadata(
            service_type=ServiceType.SAFETY_TALK,
            model="test",
            prompt_name="safety_talk",
            prompt_version="1.0.0",
            prompt_tokens=150,
            completion_tokens=300,
            total_tokens=450,
        )
        assert meta.prompt_tokens == 150
        assert meta.completion_tokens == 300
        assert meta.total_tokens == 450

    def test_serializable_to_dict(self):
        meta = ServiceMetadata(
            service_type=ServiceType.MATERIAL_REMINDER,
            model="test",
            prompt_name="material_reminder",
            prompt_version="1.0.0",
        )
        d = meta.model_dump(mode="json")
        assert d["service_type"] == "material_reminder"
        assert "generated_at" in d

    def test_generation_id_is_auto_assigned_uuid4(self):
        """Sprint 5.1: generation_id is auto-assigned as a UUID4 string."""
        import uuid
        meta = ServiceMetadata(
            service_type=ServiceType.DAILY_REPORT,
            model="test",
            prompt_name="daily_report",
            prompt_version="1.0.0",
        )
        # Must be a valid UUID4
        parsed = uuid.UUID(meta.generation_id, version=4)
        assert str(parsed) == meta.generation_id

    def test_generation_id_is_unique_per_instance(self):
        """Each ServiceMetadata gets a different UUID4."""
        kwargs = dict(
            service_type=ServiceType.DAILY_REPORT,
            model="test",
            prompt_name="daily_report",
            prompt_version="1.0.0",
        )
        ids = {ServiceMetadata(**kwargs).generation_id for _ in range(10)}
        assert len(ids) == 10  # all unique

    def test_generation_id_can_be_set_explicitly(self):
        """Explicit generation_id is respected (for correlation with events)."""
        meta = ServiceMetadata(
            generation_id="fixed-id-for-test",
            service_type=ServiceType.DAILY_REPORT,
            model="test",
            prompt_name="daily_report",
            prompt_version="1.0.0",
        )
        assert meta.generation_id == "fixed-id-for-test"

    def test_generation_id_appears_in_serialized_dict(self):
        """generation_id is included in model_dump() output."""
        meta = ServiceMetadata(
            service_type=ServiceType.SAFETY_TALK,
            model="test",
            prompt_name="safety_talk",
            prompt_version="1.0.0",
        )
        d = meta.model_dump(mode="json")
        assert "generation_id" in d
        assert len(d["generation_id"]) == 36  # UUID4 string length


# ── ServiceOutput ──────────────────────────────────────────────────────────────

class TestServiceOutput:
    def test_success_output(self):
        out = ServiceOutput(
            success=True,
            service_type=ServiceType.DAILY_REPORT,
            content="## Daily Report\n\nWork done.",
        )
        assert out.success is True
        assert "Daily Report" in out.content
        assert out.errors == []

    def test_failure_factory(self):
        out = ServiceOutput.failure(
            service_type=ServiceType.CUSTOMER_UPDATE,
            errors=["Groq API unavailable"],
        )
        assert out.success is False
        assert out.content == ""
        assert "Groq API unavailable" in out.errors
        assert out.service_type is ServiceType.CUSTOMER_UPDATE

    def test_failure_with_warnings(self):
        out = ServiceOutput.failure(
            service_type=ServiceType.SAFETY_TALK,
            errors=["Timeout"],
            warnings=["Slow response"],
        )
        assert out.warnings == ["Slow response"]

    def test_to_dict_contains_key_fields(self):
        out = ServiceOutput(
            success=True,
            service_type=ServiceType.MATERIAL_REMINDER,
            content="## Materials\n\nNone required.",
        )
        d = out.to_dict()
        assert d["success"] is True
        assert d["service_type"] == "material_reminder"
        assert "content" in d

    def test_to_json_is_valid_json(self):
        out = ServiceOutput(
            success=True,
            service_type=ServiceType.DAILY_REPORT,
            content="## Report",
        )
        parsed = json.loads(out.to_json())
        assert parsed["service_type"] == "daily_report"

    def test_errors_and_warnings_are_empty_lists_by_default(self):
        out = ServiceOutput(
            success=True,
            service_type=ServiceType.DAILY_REPORT,
        )
        assert out.errors == []
        assert out.warnings == []

    def test_metadata_is_none_by_default(self):
        out = ServiceOutput(
            success=True,
            service_type=ServiceType.DAILY_REPORT,
        )
        assert out.metadata is None


# ── Typed subclasses ───────────────────────────────────────────────────────────

class TestTypedOutputSubclasses:
    def test_daily_report_has_correct_service_type(self):
        r = DailyReport(success=True, content="## Report")
        assert r.service_type is ServiceType.DAILY_REPORT

    def test_customer_update_has_correct_service_type(self):
        u = CustomerUpdate(success=True, content="Subject: Update\nHi...")
        assert u.service_type is ServiceType.CUSTOMER_UPDATE

    def test_toolbox_talk_has_correct_service_type(self):
        t = ToolboxTalk(success=True, content="## Safety Talk\n\nPPE required.")
        assert t.service_type is ServiceType.SAFETY_TALK

    def test_material_reminder_has_correct_service_type(self):
        m = MaterialReminder(success=True, content="## Material\n\nPriority: HIGH")
        assert m.service_type is ServiceType.MATERIAL_REMINDER

    def test_all_subclasses_are_service_output(self):
        for cls in (DailyReport, CustomerUpdate, ToolboxTalk, MaterialReminder):
            assert issubclass(cls, ServiceOutput)

    def test_failure_factory_works_on_subclass(self):
        r = DailyReport.failure(
            service_type=ServiceType.DAILY_REPORT,
            errors=["failed"],
        )
        assert r.success is False
        assert r.service_type is ServiceType.DAILY_REPORT

    def test_subclass_inherits_to_json(self):
        r = DailyReport(success=True, content="## Report")
        parsed = json.loads(r.to_json())
        assert parsed["service_type"] == "daily_report"


# ── GenerationResult ───────────────────────────────────────────────────────────

def _make_result(**overrides) -> GenerationResult:
    defaults = dict(
        success=True,
        log_id="log-001",
        log_date="2024-03-15",
        current_stage="framing",
        daily_report=DailyReport(
            success=True,
            content="## Report\n\nWork Completed today.\n\nWeather: sunny\n\nWorkforce: 5 workers.",
        ),
        customer_update=CustomerUpdate(
            success=True,
            content="Subject: Project Update\n\nHi there,\nGood progress.\n\nBest regards,\nYour Construction Team",
        ),
        safety_talk=ToolboxTalk(
            success=True,
            content="## Safety Talk\n\nPPE required.\n\nSafety first.\n\nEmergency: call 911",
        ),
        material_reminder=MaterialReminder(
            success=True,
            content="## Material Reminder\n\nPriority: HIGH\n\nLumber needed.",
        ),
    )
    defaults.update(overrides)
    return GenerationResult(**defaults)


class TestGenerationResult:
    def test_successful_result(self):
        result = _make_result()
        assert result.success is True
        assert result.log_id == "log-001"
        assert result.daily_report.success is True
        assert result.customer_update.success is True

    def test_generated_at_set_automatically(self):
        before = datetime.now(timezone.utc)
        result = _make_result()
        after = datetime.now(timezone.utc)
        assert before <= result.generated_at <= after

    def test_errors_list_empty_by_default(self):
        result = _make_result()
        assert result.errors == []

    def test_failure_classmethod(self):
        result = GenerationResult.failure(
            log_id="log-002",
            log_date="2024-03-16",
            current_stage="roofing",
            errors=["Engine unavailable"],
        )
        assert result.success is False
        assert result.daily_report.success is False
        assert "Engine unavailable" in result.daily_report.errors
        assert result.errors == ["Engine unavailable"]

    def test_to_dict_contains_all_services(self):
        result = _make_result()
        d = result.to_dict()
        assert "daily_report" in d
        assert "customer_update" in d
        assert "safety_talk" in d
        assert "material_reminder" in d
        assert d["log_id"] == "log-001"

    def test_to_json_round_trip(self):
        result = _make_result()
        parsed = json.loads(result.to_json())
        assert parsed["success"] is True
        assert parsed["daily_report"]["service_type"] == "daily_report"
        assert parsed["safety_talk"]["service_type"] == "safety_talk"

    def test_partial_success_structure(self):
        """GenerationResult can hold a mix of succeeded and failed services."""
        result = _make_result(
            success=True,
            daily_report=DailyReport(success=True, content="## Report\n\nWork Completed.\nWeather: sunny.\nWorkforce: 5."),
            customer_update=CustomerUpdate(
                success=False,
                errors=["timeout"],
            ),
        )
        assert result.daily_report.success is True
        assert result.customer_update.success is False
