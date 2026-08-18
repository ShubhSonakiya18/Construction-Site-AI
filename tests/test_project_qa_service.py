"""
tests/test_project_qa_service.py — Unit tests for ProjectQAService.

Uses MockLLMProvider (no Groq key required). These tests verify the
service's own behavior — prompt assembly, context formatting, validation
wiring. They cannot verify that a real LLM honours the grounding
instruction; the prompt file carries that, and the API-level test asserts
the context the model is handed is correctly scoped.
"""
from __future__ import annotations

import pytest

from generation.config import GenerationConfig
from generation.models.outputs import ServiceType
from generation.prompts.loader import PromptLoader
from generation.services.project_qa import ProjectQAService
from generation.services.registry import DEFAULT_SERVICE_REGISTRY
from generation.validators.content_validator import ContentValidator
from tests.test_generation_services import MockLLMProvider

PROMPTS_DIR = "generation/prompts"

SAMPLE_LOGS = [
    {
        "log_date": "2026-03-15",
        "current_stage": "framing",
        "total_workers_present": 8,
        "delays": [
            {"type": "weather", "description": "Rain stopped work", "hours_lost": 3.0}
        ],
        "materials_used": [
            {"material": "2x6 studs", "quantity": 120.0, "unit": "linear_feet"}
        ],
    },
    {
        "log_date": "2026-03-14",
        "current_stage": "framing",
        "total_workers_present": 6,
        "delays": [],
        "materials_used": [],
    },
]


def _make_service(response: str = "Three hours were lost to rain on 2026-03-15.") -> ProjectQAService:
    return ProjectQAService(
        engine=MockLLMProvider(response=response),
        prompt_loader=PromptLoader(PROMPTS_DIR),
        validator=ContentValidator(),
        config=GenerationConfig.from_env(),
    )


def test_service_type_and_prompt_name():
    service = _make_service()
    assert service.service_type == ServiceType.PROJECT_QA
    assert service.prompt_name == "project_qa"


def test_registered_in_default_registry():
    assert DEFAULT_SERVICE_REGISTRY.is_registered(ServiceType.PROJECT_QA)


def test_user_message_includes_question_and_log_data():
    service = _make_service()
    message = service._build_user_message(
        {"question": "How many hours were lost to delays?", "logs": SAMPLE_LOGS}
    )
    assert "How many hours were lost to delays?" in message
    assert "2026-03-15" in message
    assert "Rain stopped work" in message
    assert "2x6 studs" in message


def test_user_message_marks_empty_context_explicitly():
    """An empty context must be visible to the model as an absence of data,
    not as a missing section it might fill in from general knowledge."""
    service = _make_service()
    message = service._build_user_message({"question": "Any delays?", "logs": []})
    assert "no approved daily logs" in message.lower()


def test_generate_returns_answer_on_success():
    service = _make_service(response="Three hours were lost to rain on 2026-03-15.")
    output = service.generate(
        {"question": "How many hours were lost?", "logs": SAMPLE_LOGS}
    )
    assert output.success is True
    assert output.service_type == ServiceType.PROJECT_QA
    assert "Three hours" in output.content
    assert output.metadata is not None
    assert output.metadata.model == "mock-model-v1"


def test_short_grounded_answer_passes_validation():
    """A truthful "not in the logs" answer is short by nature — it must not
    be rejected by the content validator's minimum-length rule."""
    service = _make_service(response="The logs do not cover that.")
    output = service.generate({"question": "What is the budget?", "logs": SAMPLE_LOGS})
    assert output.success is True


def test_empty_answer_fails_validation():
    service = _make_service(response="")
    output = service.generate({"question": "Any delays?", "logs": SAMPLE_LOGS})
    assert output.success is False
    assert any("empty" in e.lower() for e in output.errors)


def test_engine_failure_is_returned_not_raised():
    service = ProjectQAService(
        engine=MockLLMProvider(raises=RuntimeError("groq down")),
        prompt_loader=PromptLoader(PROMPTS_DIR),
        validator=ContentValidator(),
        config=GenerationConfig.from_env(),
    )
    output = service.generate({"question": "Any delays?", "logs": SAMPLE_LOGS})
    assert output.success is False
    assert output.content == ""
