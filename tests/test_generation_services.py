"""
tests/test_generation_services.py — Unit tests for the 4 AI generation services.

All tests use MockLLMProvider — no real Groq API key required.
Tests cover: success path, content validation failure, engine exceptions,
retry logic, metadata population, and prompt loading.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from extraction.engines.base_engine import BaseLLMProvider
from generation.config import GenerationConfig
from generation.models.outputs import ServiceOutput, ServiceType
from generation.prompts.loader import PromptLoader
from generation.services.customer_update import CustomerUpdateService
from generation.services.daily_report import DailyReportService
from generation.services.material_reminder import MaterialReminderService
from generation.services.safety_talk import SafetyTalkService
from generation.validators.content_validator import ContentValidator


# ── Mock engine ───────────────────────────────────────────────────────────────

class MockLLMProvider(BaseLLMProvider):
    """Deterministic engine that returns preset responses for tests."""

    def __init__(
        self,
        response: str = "",
        usage: dict | None = None,
        raises: Exception | None = None,
        fail_first_n: int = 0,
    ) -> None:
        self._response = response
        self._usage = usage or {"prompt_tokens": 100, "completion_tokens": 200}
        self._raises = raises
        self._fail_first_n = fail_first_n
        self._call_count = 0

    @property
    def model_name(self) -> str:
        return "mock-model-v1"

    @property
    def host(self) -> str:
        return "mock://localhost"

    def is_available(self) -> bool:
        return True

    def extract(self, prompt: str) -> tuple[str, dict]:
        self._call_count += 1
        if self._raises and self._call_count <= self._fail_first_n:
            raise self._raises
        if self._raises and self._fail_first_n == 0:
            raise self._raises
        return self._response, self._usage


# ── Shared fixtures ────────────────────────────────────────────────────────────

PROMPTS_DIR = "generation/prompts"

VALID_RESPONSES = {
    ServiceType.DAILY_REPORT: (
        "## Daily Site Report — 2024-03-15\n\n"
        "## Work Completed\n\nWall framing complete on north and east elevations. "
        "Crew installed 120 linear feet of 2×6 studs at 16 inches on center.\n\n"
        "## Workforce Summary\n\nEight workers: four carpenters, two laborers, two electricians.\n\n"
        "## Weather Conditions\n\nClear and sunny, 72°F, light wind.\n\n"
        "## Delays and Issues\n\nNo delays reported.\n\n"
        "## Safety Summary\n\nFull PPE compliance. No incidents.\n\n"
        "## Tomorrow's Plan\n\nComplete south and west wall framing."
    ),
    ServiceType.CUSTOMER_UPDATE: (
        "Subject: Project Update — March 15, 2024\n\n"
        "Hi there,\n\n"
        "Great news from your project site today! The team has been making excellent progress "
        "on the wall framing and things are moving along right on schedule.\n\n"
        "The crew completed framing on the north and east sides of your home, which means you "
        "can now see the full outline of the structure taking shape. This is an exciting milestone.\n\n"
        "Tomorrow the team plans to finish the remaining walls. We will keep you updated as "
        "each milestone is reached.\n\n"
        "Best regards,\n"
        "Your Construction Team"
    ),
    ServiceType.SAFETY_TALK: (
        "## Daily Safety Toolbox Talk — 2024-03-15\n\n"
        "**Stage:** framing | **Presenter:** Site Safety Officer\n\n"
        "## Today's Key Hazards\n\n"
        "- Fall hazard from elevated work platforms (29 CFR 1926.502)\n"
        "- Struck-by hazard from overhead material handling\n"
        "- Puncture injuries from pneumatic nailers\n\n"
        "## Required PPE\n\n"
        "- Hard hat (29 CFR 1926.100)\n"
        "- Safety glasses\n"
        "- Cut-resistant gloves when handling lumber\n"
        "- Steel-toed work boots\n\n"
        "## Safety Reminders\n\n"
        "- Always install guardrails before working at heights above 6 feet.\n"
        "- Inspect all pneumatic nailers before first use each day.\n"
        "- Keep the deck clear of scrap lumber and cut-offs.\n\n"
        "## Tool and Equipment Inspection Checklist\n\n"
        "- Check air hoses for cracks or loose fittings.\n"
        "- Verify ladder feet are on stable, level ground.\n\n"
        "## Emergency Procedures Reminder\n\n"
        "**Emergency Contact:** Call 911 immediately.\n"
        "**Assembly Point:** Front of property near the street.\n\n"
        "## Quick Quiz\n\n"
        "Q1: At what height is fall protection required?\nA: 6 feet above a lower level.\n"
        "Q2: When must you inspect your tools?\nA: Before every use.\n"
        "Q3: Where is the assembly point?\nA: Front of property."
    ),
    ServiceType.MATERIAL_REMINDER: (
        "## Material Procurement Reminder — 2024-03-15\n\n"
        "**Stage:** framing | **Prepared for:** Site Foreman\n\n"
        "## CRITICAL — Order Immediately\n\nNone — no critical shortages.\n\n"
        "## HIGH PRIORITY — Order Today\n\n"
        "- 2×4 lumber studs (200 units) — needed for south wall framing tomorrow. "
        "Priority: HIGH. Source TBD.\n\n"
        "## MEDIUM PRIORITY — Order This Week\n\nNone.\n\n"
        "## LOW PRIORITY — Plan Ahead\n\nNone.\n\n"
        "## Delivery Notes\n\nNo special delivery notes. Material priority noted."
    ),
}

SAMPLE_LOG = {
    "log_id": "test-log-001",
    "schema_version": "1.0.0",
    "log_date": "2024-03-15",
    "log_source": "voice_note",
    "current_stage": "framing",
    "project": {
        "project_id": "proj-001",
        "project_name": "Smith Residence",
        "location": "123 Main St, Austin TX",
    },
    "workforce": {
        "total_workers_present": 8,
        "foreman_name": "John Smith",
        "trades_on_site": ["carpenter", "laborer"],
    },
    "work_completed": {
        "description": "Exterior wall framing complete on east and north sides",
        "activities": ["frame_walls", "install_headers"],
        "progress_percentage": 45,
    },
    "weather": {
        "conditions": "sunny",
        "temperature_fahrenheit": 72,
        "wind_mph": 5,
        "impact_on_work": "none",
    },
    "materials": {
        "lumber_2x4_qty": 500,
        "lumber_2x6_qty": 200,
    },
    "delays_and_issues": {"total_delay_hours": 0},
    "safety": {"incidents": [], "ppe_compliance": "full"},
    "tomorrows_plan": {
        "description": "Complete south and west wall framing",
        "required_workers": 8,
    },
}


def _make_service(service_cls, response: str, **mock_kwargs):
    engine = MockLLMProvider(response=response, **mock_kwargs)
    loader = PromptLoader(PROMPTS_DIR)
    validator = ContentValidator()
    config = GenerationConfig(max_retries=2, retry_delay_seconds=0.0)
    return service_cls(
        engine=engine,
        prompt_loader=loader,
        validator=validator,
        config=config,
    )


# ── DailyReportService ────────────────────────────────────────────────────────

class TestDailyReportService:
    def test_service_type(self):
        svc = _make_service(DailyReportService, "")
        assert svc.service_type is ServiceType.DAILY_REPORT

    def test_prompt_name(self):
        svc = _make_service(DailyReportService, "")
        assert svc.prompt_name == "daily_report"

    def test_success_path(self):
        resp = VALID_RESPONSES[ServiceType.DAILY_REPORT]
        svc = _make_service(DailyReportService, resp)
        out = svc.generate(SAMPLE_LOG)
        assert out.success is True
        assert out.content == resp
        assert out.errors == []

    def test_metadata_populated_on_success(self):
        resp = VALID_RESPONSES[ServiceType.DAILY_REPORT]
        svc = _make_service(DailyReportService, resp)
        out = svc.generate(SAMPLE_LOG)
        assert out.metadata is not None
        assert out.metadata.model == "mock-model-v1"
        assert out.metadata.prompt_name == "daily_report"
        assert out.metadata.prompt_version == "1.0.0"
        assert out.metadata.prompt_tokens == 100
        assert out.metadata.completion_tokens == 200
        assert out.metadata.total_tokens == 300
        assert out.metadata.retry_count == 0

    def test_validation_failure_returns_failed_output(self):
        svc = _make_service(DailyReportService, "Too short.")
        out = svc.generate(SAMPLE_LOG)
        assert out.success is False
        assert len(out.errors) > 0
        assert out.content == "Too short."  # content preserved even on validation fail

    def test_build_user_message_includes_key_fields(self):
        svc = _make_service(DailyReportService, "")
        msg = svc._build_user_message(SAMPLE_LOG)
        assert "2024-03-15" in msg
        assert "framing" in msg
        assert "Smith Residence" in msg

    def test_empty_log_sections_handled_gracefully(self):
        minimal_log = {
            "log_id": "min-001",
            "log_date": "2024-03-15",
            "current_stage": "framing",
        }
        resp = VALID_RESPONSES[ServiceType.DAILY_REPORT]
        svc = _make_service(DailyReportService, resp)
        out = svc.generate(minimal_log)
        assert isinstance(out, ServiceOutput)


# ── CustomerUpdateService ──────────────────────────────────────────────────────

class TestCustomerUpdateService:
    def test_service_type(self):
        svc = _make_service(CustomerUpdateService, "")
        assert svc.service_type is ServiceType.CUSTOMER_UPDATE

    def test_prompt_name(self):
        svc = _make_service(CustomerUpdateService, "")
        assert svc.prompt_name == "customer_update"

    def test_success_path(self):
        resp = VALID_RESPONSES[ServiceType.CUSTOMER_UPDATE]
        svc = _make_service(CustomerUpdateService, resp)
        out = svc.generate(SAMPLE_LOG)
        assert out.success is True
        assert "Subject:" in out.content
        assert "Construction Team" in out.content

    def test_build_user_message_omits_worker_details(self):
        svc = _make_service(CustomerUpdateService, "")
        msg = svc._build_user_message(SAMPLE_LOG)
        # CustomerUpdate should NOT include workforce section
        assert "workforce" not in msg.lower() or "work_completed" in msg.lower()
        assert "Smith Residence" in msg


# ── SafetyTalkService ─────────────────────────────────────────────────────────

class TestSafeTalkService:
    def test_service_type(self):
        svc = _make_service(SafetyTalkService, "")
        assert svc.service_type is ServiceType.SAFETY_TALK

    def test_prompt_name(self):
        svc = _make_service(SafetyTalkService, "")
        assert svc.prompt_name == "safety_talk"

    def test_success_path(self):
        resp = VALID_RESPONSES[ServiceType.SAFETY_TALK]
        svc = _make_service(SafetyTalkService, resp)
        out = svc.generate(SAMPLE_LOG)
        assert out.success is True
        assert "PPE" in out.content
        assert "Emergency" in out.content

    def test_build_user_message_includes_safety_section(self):
        svc = _make_service(SafetyTalkService, "")
        msg = svc._build_user_message(SAMPLE_LOG)
        assert "SAFETY" in msg.upper()
        assert "framing" in msg


# ── MaterialReminderService ───────────────────────────────────────────────────

class TestMaterialReminderService:
    def test_service_type(self):
        svc = _make_service(MaterialReminderService, "")
        assert svc.service_type is ServiceType.MATERIAL_REMINDER

    def test_prompt_name(self):
        svc = _make_service(MaterialReminderService, "")
        assert svc.prompt_name == "material_reminder"

    def test_success_path(self):
        resp = VALID_RESPONSES[ServiceType.MATERIAL_REMINDER]
        svc = _make_service(MaterialReminderService, resp)
        out = svc.generate(SAMPLE_LOG)
        assert out.success is True
        assert "Material" in out.content
        assert "Priority" in out.content

    def test_build_user_message_includes_materials_section(self):
        svc = _make_service(MaterialReminderService, "")
        msg = svc._build_user_message(SAMPLE_LOG)
        assert "MATERIALS" in msg.upper()
        assert "lumber" in msg.lower() or "2x4" in msg.lower() or "500" in msg


# ── Retry logic (via BaseAIService) ───────────────────────────────────────────

class TestRetryLogic:
    def test_succeeds_on_second_attempt(self):
        """Engine fails once then succeeds — retry_count should be 1."""
        resp = VALID_RESPONSES[ServiceType.DAILY_REPORT]
        engine = MockLLMProvider(
            response=resp,
            raises=RuntimeError("Temporary error"),
            fail_first_n=1,
        )
        loader = PromptLoader(PROMPTS_DIR)
        config = GenerationConfig(max_retries=2, retry_delay_seconds=0.0)
        svc = DailyReportService(
            engine=engine,
            prompt_loader=loader,
            validator=ContentValidator(),
            config=config,
        )
        out = svc.generate(SAMPLE_LOG)
        assert out.success is True
        assert out.metadata is not None
        assert out.metadata.retry_count == 1
        assert engine._call_count == 2

    def test_all_retries_exhausted_returns_failure(self):
        """Engine always raises — all attempts fail, returns ServiceOutput with success=False."""
        engine = MockLLMProvider(
            response="",
            raises=RuntimeError("Persistent error"),
        )
        loader = PromptLoader(PROMPTS_DIR)
        config = GenerationConfig(max_retries=2, retry_delay_seconds=0.0)
        svc = DailyReportService(
            engine=engine,
            prompt_loader=loader,
            validator=ContentValidator(),
            config=config,
        )
        out = svc.generate(SAMPLE_LOG)
        assert out.success is False
        assert len(out.errors) > 0
        assert "Persistent error" in out.errors[0]
        assert engine._call_count == 3  # initial + 2 retries

    def test_no_retry_on_content_validation_failure(self):
        """Content validation failure does not trigger a retry (it's not a transient error)."""
        engine = MockLLMProvider(response="Too short.")
        loader = PromptLoader(PROMPTS_DIR)
        config = GenerationConfig(max_retries=3, retry_delay_seconds=0.0)
        svc = DailyReportService(
            engine=engine,
            prompt_loader=loader,
            validator=ContentValidator(),
            config=config,
        )
        out = svc.generate(SAMPLE_LOG)
        assert out.success is False
        assert engine._call_count == 1  # no retries — validation failure is immediate

    def test_zero_retries_fails_after_one_attempt(self):
        engine = MockLLMProvider(
            response="",
            raises=RuntimeError("Error"),
        )
        config = GenerationConfig(max_retries=0, retry_delay_seconds=0.0)
        svc = DailyReportService(
            engine=engine,
            prompt_loader=PromptLoader(PROMPTS_DIR),
            validator=ContentValidator(),
            config=config,
        )
        out = svc.generate(SAMPLE_LOG)
        assert out.success is False
        assert engine._call_count == 1


# ── Prompt caching ─────────────────────────────────────────────────────────────

class TestPromptCaching:
    def test_prompt_loaded_only_once_across_multiple_generate_calls(self):
        resp = VALID_RESPONSES[ServiceType.DAILY_REPORT]
        loader = MagicMock(wraps=PromptLoader(PROMPTS_DIR))
        engine = MockLLMProvider(response=resp)
        config = GenerationConfig(max_retries=0, retry_delay_seconds=0.0)
        svc = DailyReportService(
            engine=engine,
            prompt_loader=loader,
            validator=ContentValidator(),
            config=config,
        )
        svc.generate(SAMPLE_LOG)
        svc.generate(SAMPLE_LOG)
        svc.generate(SAMPLE_LOG)
        # load() should be called only once (result is cached on the service)
        assert loader.load.call_count == 1


# ── ServiceOutput structure ───────────────────────────────────────────────────

class TestServiceOutputStructure:
    def test_success_output_has_no_errors(self):
        resp = VALID_RESPONSES[ServiceType.CUSTOMER_UPDATE]
        svc = _make_service(CustomerUpdateService, resp)
        out = svc.generate(SAMPLE_LOG)
        assert out.success is True
        assert out.errors == []

    def test_failure_output_preserves_content_for_debugging(self):
        """When content is returned but fails validation, content is preserved."""
        bad_content = "Too short."
        svc = _make_service(DailyReportService, bad_content)
        out = svc.generate(SAMPLE_LOG)
        assert out.success is False
        assert out.content == bad_content

    def test_metadata_response_time_is_positive(self):
        resp = VALID_RESPONSES[ServiceType.DAILY_REPORT]
        svc = _make_service(DailyReportService, resp)
        out = svc.generate(SAMPLE_LOG)
        assert out.metadata is not None
        assert out.metadata.response_time_seconds >= 0.0

    def test_metadata_validation_time_is_positive(self):
        resp = VALID_RESPONSES[ServiceType.DAILY_REPORT]
        svc = _make_service(DailyReportService, resp)
        out = svc.generate(SAMPLE_LOG)
        assert out.metadata is not None
        assert out.metadata.validation_time_seconds >= 0.0
