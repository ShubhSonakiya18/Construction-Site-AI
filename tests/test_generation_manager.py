"""
tests/test_generation_manager.py — Unit tests for AIServiceManager.

All tests inject MockLLMProvider — no real Groq API key required.
Tests cover: generate_all(), generate() single service, is_available(),
partial failures, dependency injection, and GenerationResult structure.
"""
from __future__ import annotations

import pytest

from extraction.engines.base_engine import BaseLLMProvider
from generation.config import GenerationConfig
from generation.manager import AIServiceManager
from generation.models.outputs import (
    CustomerUpdate,
    DailyReport,
    GenerationResult,
    MaterialReminder,
    ServiceOutput,
    ServiceType,
    ToolboxTalk,
)


# ── Mock engine ───────────────────────────────────────────────────────────────

class MockLLMProvider(BaseLLMProvider):
    def __init__(
        self,
        responses: dict[ServiceType, str] | None = None,
        default_response: str = "",
        raises: Exception | None = None,
        available: bool = True,
    ) -> None:
        self._responses = responses or {}
        self._default = default_response
        self._raises = raises
        self._available = available
        self.call_count = 0

    @property
    def model_name(self) -> str:
        return "mock-model-v1"

    @property
    def host(self) -> str:
        return "mock://localhost"

    def is_available(self) -> bool:
        return self._available

    def extract(self, prompt: str) -> tuple[str, dict]:
        self.call_count += 1
        if self._raises:
            raise self._raises
        return self._default, {"prompt_tokens": 100, "completion_tokens": 200}


VALID_RESPONSES = {
    ServiceType.DAILY_REPORT: (
        "## Daily Site Report — 2024-03-15\n\n"
        "## Work Completed\n\nWall framing complete on north and east elevations.\n\n"
        "## Workforce Summary\n\nEight workers: four carpenters, two laborers.\n\n"
        "## Weather Conditions\n\nClear and sunny, 72°F.\n\n"
        "## Delays and Issues\n\nNo delays.\n\n"
        "## Safety Summary\n\nFull PPE compliance.\n\n"
        "## Tomorrow's Plan\n\nComplete south and west wall framing."
    ),
    ServiceType.CUSTOMER_UPDATE: (
        "Subject: Project Update — March 15, 2024\n\n"
        "Hi there,\n\nGreat progress on your home today! The crew finished framing the north "
        "and east walls. Everything is on schedule and the team is doing excellent work.\n\n"
        "Tomorrow they will complete the remaining walls. It is exciting to see the progress.\n\n"
        "Best regards,\n"
        "Your Construction Team"
    ),
    ServiceType.SAFETY_TALK: (
        "## Daily Safety Toolbox Talk — 2024-03-15\n\n"
        "**Stage:** framing\n\n"
        "## Today's Key Hazards\n\n- Fall hazard (29 CFR 1926.502)\n- Struck-by hazard\n\n"
        "## Required PPE\n\n- Hard hat (29 CFR 1926.100)\n- Safety glasses\n- Steel-toed boots\n\n"
        "## Safety Reminders\n\n- Always install guardrails before working at heights.\n"
        "- Inspect all pneumatic nailers before first use.\n\n"
        "## Tool and Equipment Inspection Checklist\n\n"
        "- Check air hoses for cracks.\n- Verify ladder placement.\n\n"
        "## Emergency Procedures Reminder\n\n"
        "**Emergency Contact:** Call 911.\n**Assembly Point:** Front of property.\n\n"
        "## Quick Quiz\n\n"
        "Q1: At what height is fall protection required?\nA: 6 feet.\n"
        "Q2: When must you inspect tools?\nA: Before every use.\n"
        "Q3: Assembly point?\nA: Front of property."
    ),
    ServiceType.MATERIAL_REMINDER: (
        "## Material Procurement Reminder — 2024-03-15\n\n"
        "**Stage:** framing | **Prepared for:** Site Foreman\n\n"
        "## CRITICAL — Order Immediately\n\nNone.\n\n"
        "## HIGH PRIORITY — Order Today\n\n"
        "- 2×4 lumber (200 units). Priority: HIGH.\n\n"
        "## MEDIUM PRIORITY — Order This Week\n\nNone.\n\n"
        "## LOW PRIORITY — Plan Ahead\n\nNone.\n\n"
        "## Delivery Notes\n\nNo special delivery notes."
    ),
}

SAMPLE_LOG = {
    "log_id": "mgr-test-001",
    "schema_version": "1.0.0",
    "log_date": "2024-03-15",
    "log_source": "voice_note",
    "current_stage": "framing",
    "project": {"project_id": "proj-001", "project_name": "Smith Residence"},
    "workforce": {"total_workers_present": 8},
    "work_completed": {"description": "North and east wall framing complete"},
    "weather": {"conditions": "sunny"},
    "materials": {"lumber_2x4_qty": 500},
    "delays_and_issues": {"total_delay_hours": 0},
    "safety": {"incidents": [], "ppe_compliance": "full"},
    "tomorrows_plan": {"description": "Complete south and west wall framing"},
}


def _make_manager(response: str = "", raises: Exception | None = None) -> AIServiceManager:
    """Create manager with a mock engine returning one response for all services."""
    engine = MockLLMProvider(default_response=response, raises=raises)
    config = GenerationConfig(max_retries=1, retry_delay_seconds=0.0)
    return AIServiceManager(config=config, engine=engine)


def _make_all_success_manager() -> AIServiceManager:
    """Manager whose engine always returns a valid response (rotated per-call)."""
    responses = list(VALID_RESPONSES.values())
    call_index = [0]

    class RotatingMock(BaseLLMProvider):
        @property
        def model_name(self): return "mock-v1"
        @property
        def host(self): return "mock://localhost"
        def is_available(self): return True
        def extract(self, prompt):
            resp = responses[call_index[0] % len(responses)]
            call_index[0] += 1
            return resp, {"prompt_tokens": 50, "completion_tokens": 100}

    config = GenerationConfig(max_retries=0, retry_delay_seconds=0.0)
    return AIServiceManager(config=config, engine=RotatingMock())


# ── is_available ──────────────────────────────────────────────────────────────

class TestIsAvailable:
    def test_delegates_to_engine_true(self):
        engine = MockLLMProvider(available=True)
        manager = AIServiceManager(config=GenerationConfig(), engine=engine)
        assert manager.is_available() is True

    def test_delegates_to_engine_false(self):
        engine = MockLLMProvider(available=False)
        manager = AIServiceManager(config=GenerationConfig(), engine=engine)
        assert manager.is_available() is False


# ── generate() single service ─────────────────────────────────────────────────

class TestGenerateSingleService:
    def test_generate_daily_report(self):
        manager = _make_manager(VALID_RESPONSES[ServiceType.DAILY_REPORT])
        out = manager.generate(ServiceType.DAILY_REPORT, SAMPLE_LOG)
        assert isinstance(out, ServiceOutput)
        assert out.service_type is ServiceType.DAILY_REPORT

    def test_generate_customer_update(self):
        manager = _make_manager(VALID_RESPONSES[ServiceType.CUSTOMER_UPDATE])
        out = manager.generate(ServiceType.CUSTOMER_UPDATE, SAMPLE_LOG)
        assert out.service_type is ServiceType.CUSTOMER_UPDATE

    def test_generate_safety_talk(self):
        manager = _make_manager(VALID_RESPONSES[ServiceType.SAFETY_TALK])
        out = manager.generate(ServiceType.SAFETY_TALK, SAMPLE_LOG)
        assert out.service_type is ServiceType.SAFETY_TALK

    def test_generate_material_reminder(self):
        manager = _make_manager(VALID_RESPONSES[ServiceType.MATERIAL_REMINDER])
        out = manager.generate(ServiceType.MATERIAL_REMINDER, SAMPLE_LOG)
        assert out.service_type is ServiceType.MATERIAL_REMINDER

    def test_generate_unknown_service_raises_value_error(self):
        manager = _make_manager()
        with pytest.raises((ValueError, KeyError)):
            manager.generate("nonexistent_service", SAMPLE_LOG)  # type: ignore[arg-type]


# ── generate_all() ────────────────────────────────────────────────────────────

class TestGenerateAll:
    def test_returns_generation_result(self):
        manager = _make_all_success_manager()
        result = manager.generate_all(SAMPLE_LOG)
        assert isinstance(result, GenerationResult)

    def test_result_has_all_four_outputs(self):
        manager = _make_all_success_manager()
        result = manager.generate_all(SAMPLE_LOG)
        assert isinstance(result.daily_report, DailyReport)
        assert isinstance(result.customer_update, CustomerUpdate)
        assert isinstance(result.safety_talk, ToolboxTalk)
        assert isinstance(result.material_reminder, MaterialReminder)

    def test_result_log_id_and_date_populated(self):
        manager = _make_all_success_manager()
        result = manager.generate_all(SAMPLE_LOG)
        assert result.log_id == "mgr-test-001"
        assert result.log_date == "2024-03-15"
        assert result.current_stage == "framing"

    def test_all_succeed_result_success_true(self):
        manager = _make_all_success_manager()
        result = manager.generate_all(SAMPLE_LOG)
        assert result.success is True

    def test_all_fail_result_success_false(self):
        manager = _make_manager(raises=RuntimeError("API down"))
        result = manager.generate_all(SAMPLE_LOG)
        assert result.success is False
        assert result.daily_report.success is False
        assert result.customer_update.success is False
        assert result.safety_talk.success is False
        assert result.material_reminder.success is False

    def test_all_fail_result_contains_errors(self):
        manager = _make_manager(raises=RuntimeError("API down"))
        result = manager.generate_all(SAMPLE_LOG)
        assert len(result.errors) > 0

    def test_empty_log_does_not_raise(self):
        """Manager handles a minimal log dict without crashing."""
        manager = _make_all_success_manager()
        result = manager.generate_all({
            "log_id": "empty-001",
            "log_date": "2024-03-15",
            "current_stage": "framing",
        })
        assert isinstance(result, GenerationResult)

    def test_log_with_none_sections_does_not_raise(self):
        log = dict(SAMPLE_LOG, workforce=None, materials=None, safety=None)
        manager = _make_all_success_manager()
        result = manager.generate_all(log)
        assert isinstance(result, GenerationResult)

    def test_engine_called_four_times(self):
        engine = MockLLMProvider(
            default_response=VALID_RESPONSES[ServiceType.DAILY_REPORT]
        )
        config = GenerationConfig(max_retries=0, retry_delay_seconds=0.0)
        manager = AIServiceManager(config=config, engine=engine)
        manager.generate_all(SAMPLE_LOG)
        assert engine.call_count == 4


# ── Dependency injection ──────────────────────────────────────────────────────

class TestDependencyInjection:
    def test_custom_engine_injected(self):
        custom_engine = MockLLMProvider(
            default_response=VALID_RESPONSES[ServiceType.DAILY_REPORT]
        )
        manager = AIServiceManager(engine=custom_engine)
        result = manager.generate(ServiceType.DAILY_REPORT, SAMPLE_LOG)
        assert custom_engine.call_count == 1

    def test_custom_config_injected(self):
        config = GenerationConfig(max_retries=0, retry_delay_seconds=0.0)
        engine = MockLLMProvider(
            default_response=VALID_RESPONSES[ServiceType.MATERIAL_REMINDER]
        )
        manager = AIServiceManager(config=config, engine=engine)
        assert manager._config.max_retries == 0

    def test_default_config_loaded_from_env_when_not_provided(self, monkeypatch):
        monkeypatch.setenv("GENERATION_MAX_RETRIES", "7")
        engine = MockLLMProvider()
        manager = AIServiceManager(engine=engine)
        assert manager._config.max_retries == 7


# ── GenerationResult serialization ───────────────────────────────────────────

class TestGenerationResultSerialization:
    def test_to_json_is_valid_json(self):
        import json
        manager = _make_all_success_manager()
        result = manager.generate_all(SAMPLE_LOG)
        parsed = json.loads(result.to_json())
        assert "daily_report" in parsed
        assert "customer_update" in parsed
        assert "safety_talk" in parsed
        assert "material_reminder" in parsed

    def test_to_dict_has_correct_types(self):
        manager = _make_all_success_manager()
        result = manager.generate_all(SAMPLE_LOG)
        d = result.to_dict()
        assert isinstance(d["log_id"], str)
        assert isinstance(d["daily_report"], dict)
        assert isinstance(d["errors"], list)

    def test_failure_result_serializes(self):
        import json
        manager = _make_manager(raises=RuntimeError("down"))
        result = manager.generate_all(SAMPLE_LOG)
        parsed = json.loads(result.to_json())
        assert parsed["success"] is False
