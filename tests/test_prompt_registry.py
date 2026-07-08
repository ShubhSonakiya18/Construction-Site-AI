"""
tests/test_prompt_registry.py — Unit tests for Sprint 5.1 PromptRegistry.

Tests cover:
  - register() and get()
  - is_registered() check
  - list_names() returns sorted list
  - validate() raises ValueError for unknown names
  - get() raises KeyError for unknown names
  - Overwrite warning on duplicate register
  - DEFAULT_PROMPT_REGISTRY has all 4 built-in prompts
  - PromptRegistration fields are correct for built-in prompts
  - len() reflects registration count
"""
from __future__ import annotations

import pytest

from generation.prompts.registry import (
    DEFAULT_PROMPT_REGISTRY,
    PromptRegistration,
    PromptRegistry,
)


# ── PromptRegistry basic operations ──────────────────────────────────────────

class TestPromptRegistryBasics:
    def test_empty_registry_has_no_names(self):
        reg = PromptRegistry()
        assert reg.list_names() == []

    def test_register_and_get(self):
        reg = PromptRegistry()
        entry = PromptRegistration(
            name="test_prompt",
            description="A test prompt",
            expected_output="markdown",
            service_class_name="TestService",
        )
        reg.register(entry)
        result = reg.get("test_prompt")
        assert result.name == "test_prompt"
        assert result.description == "A test prompt"

    def test_register_returns_self_for_chaining(self):
        reg = PromptRegistry()
        result = reg.register(PromptRegistration(
            name="x", description="", expected_output="markdown", service_class_name="X"
        ))
        assert result is reg

    def test_is_registered_true_after_register(self):
        reg = PromptRegistry()
        reg.register(PromptRegistration(
            name="foo", description="", expected_output="markdown", service_class_name="Foo"
        ))
        assert reg.is_registered("foo") is True

    def test_is_registered_false_for_unknown(self):
        reg = PromptRegistry()
        assert reg.is_registered("not_registered") is False

    def test_list_names_returns_sorted_list(self):
        reg = PromptRegistry()
        for name in ["zzz", "aaa", "mmm"]:
            reg.register(PromptRegistration(
                name=name, description="", expected_output="markdown", service_class_name="S"
            ))
        assert reg.list_names() == ["aaa", "mmm", "zzz"]

    def test_len_reflects_count(self):
        reg = PromptRegistry()
        assert len(reg) == 0
        reg.register(PromptRegistration(
            name="a", description="", expected_output="markdown", service_class_name="A"
        ))
        reg.register(PromptRegistration(
            name="b", description="", expected_output="markdown", service_class_name="B"
        ))
        assert len(reg) == 2


# ── Error cases ───────────────────────────────────────────────────────────────

class TestPromptRegistryErrors:
    def test_get_unknown_raises_key_error(self):
        reg = PromptRegistry()
        with pytest.raises(KeyError, match="not registered"):
            reg.get("nonexistent")

    def test_validate_known_does_not_raise(self):
        reg = PromptRegistry()
        reg.register(PromptRegistration(
            name="ok", description="", expected_output="markdown", service_class_name="Ok"
        ))
        reg.validate("ok")  # should not raise

    def test_validate_unknown_raises_value_error(self):
        reg = PromptRegistry()
        with pytest.raises(ValueError, match="not registered"):
            reg.validate("missing")

    def test_validate_error_includes_known_names(self):
        reg = PromptRegistry()
        reg.register(PromptRegistration(
            name="daily_report", description="", expected_output="markdown", service_class_name="DRS"
        ))
        with pytest.raises(ValueError) as exc_info:
            reg.validate("unknown_prompt")
        assert "daily_report" in str(exc_info.value)

    def test_duplicate_register_overwrites(self):
        reg = PromptRegistry()
        reg.register(PromptRegistration(
            name="dup", description="First", expected_output="markdown", service_class_name="A"
        ))
        reg.register(PromptRegistration(
            name="dup", description="Second", expected_output="email", service_class_name="B"
        ))
        entry = reg.get("dup")
        assert entry.description == "Second"
        assert entry.expected_output == "email"


# ── PromptRegistration fields ─────────────────────────────────────────────────

class TestPromptRegistration:
    def test_variables_default_to_empty_list(self):
        entry = PromptRegistration(
            name="test", description="", expected_output="markdown", service_class_name="S"
        )
        assert entry.variables == []

    def test_min_body_length_default(self):
        entry = PromptRegistration(
            name="test", description="", expected_output="markdown", service_class_name="S"
        )
        assert entry.min_body_length == 50

    def test_custom_variables_and_length(self):
        entry = PromptRegistration(
            name="test",
            description="desc",
            expected_output="json",
            service_class_name="S",
            variables=["date", "stage"],
            min_body_length=200,
        )
        assert entry.variables == ["date", "stage"]
        assert entry.min_body_length == 200


# ── DEFAULT_PROMPT_REGISTRY ───────────────────────────────────────────────────

class TestDefaultPromptRegistry:
    def test_has_four_built_in_prompts(self):
        assert len(DEFAULT_PROMPT_REGISTRY) == 4

    def test_all_four_names_registered(self):
        names = DEFAULT_PROMPT_REGISTRY.list_names()
        assert "daily_report" in names
        assert "customer_update" in names
        assert "safety_talk" in names
        assert "material_reminder" in names

    def test_daily_report_expected_output_is_markdown(self):
        entry = DEFAULT_PROMPT_REGISTRY.get("daily_report")
        assert entry.expected_output == "markdown"

    def test_customer_update_expected_output_is_email(self):
        entry = DEFAULT_PROMPT_REGISTRY.get("customer_update")
        assert entry.expected_output == "email"

    def test_safety_talk_expected_output_is_markdown(self):
        entry = DEFAULT_PROMPT_REGISTRY.get("safety_talk")
        assert entry.expected_output == "markdown"

    def test_material_reminder_expected_output_is_markdown(self):
        entry = DEFAULT_PROMPT_REGISTRY.get("material_reminder")
        assert entry.expected_output == "markdown"

    def test_all_entries_have_descriptions(self):
        for name in DEFAULT_PROMPT_REGISTRY.list_names():
            entry = DEFAULT_PROMPT_REGISTRY.get(name)
            assert len(entry.description) > 0

    def test_all_entries_have_service_class_name(self):
        for name in DEFAULT_PROMPT_REGISTRY.list_names():
            entry = DEFAULT_PROMPT_REGISTRY.get(name)
            assert entry.service_class_name.endswith("Service")

    def test_all_entries_have_variables(self):
        for name in DEFAULT_PROMPT_REGISTRY.list_names():
            entry = DEFAULT_PROMPT_REGISTRY.get(name)
            assert len(entry.variables) > 0

    def test_validate_all_built_ins_does_not_raise(self):
        for name in ["daily_report", "customer_update", "safety_talk", "material_reminder"]:
            DEFAULT_PROMPT_REGISTRY.validate(name)  # should not raise
