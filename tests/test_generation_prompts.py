"""
tests/test_generation_prompts.py — Unit tests for PromptLoader and PromptMetadata.

Tests cover: loading real prompt files, frontmatter parsing (scalars + lists),
versioning metadata, caching, error handling, and bodies without frontmatter.
No LLM calls. Uses real prompt files from generation/prompts/.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from generation.prompts.loader import LoadedPrompt, PromptLoader, PromptMetadata


PROMPTS_DIR = Path("generation/prompts")
ALL_PROMPT_NAMES = ["daily_report", "customer_update", "safety_talk", "material_reminder"]


# ── PromptLoader.list_available ────────────────────────────────────────────────

class TestListAvailable:
    def test_all_four_prompts_listed(self):
        loader = PromptLoader(PROMPTS_DIR)
        available = loader.list_available()
        for name in ALL_PROMPT_NAMES:
            assert name in available

    def test_returns_sorted_list(self):
        loader = PromptLoader(PROMPTS_DIR)
        available = loader.list_available()
        assert available == sorted(available)

    def test_nonexistent_dir_returns_empty(self):
        loader = PromptLoader("/nonexistent/dir")
        assert loader.list_available() == []


# ── PromptLoader.load — real prompt files ─────────────────────────────────────

class TestLoadRealPrompts:
    @pytest.mark.parametrize("name", ALL_PROMPT_NAMES)
    def test_load_returns_loaded_prompt(self, name):
        loader = PromptLoader(PROMPTS_DIR)
        result = loader.load(name)
        assert isinstance(result, LoadedPrompt)

    @pytest.mark.parametrize("name", ALL_PROMPT_NAMES)
    def test_metadata_name_matches_file(self, name):
        loader = PromptLoader(PROMPTS_DIR)
        result = loader.load(name)
        assert result.metadata.name == name

    @pytest.mark.parametrize("name", ALL_PROMPT_NAMES)
    def test_version_is_semver(self, name):
        loader = PromptLoader(PROMPTS_DIR)
        result = loader.load(name)
        parts = result.metadata.version.split(".")
        assert len(parts) == 3
        for part in parts:
            assert part.isdigit(), f"Version part '{part}' is not numeric"

    @pytest.mark.parametrize("name", ALL_PROMPT_NAMES)
    def test_supported_models_is_list(self, name):
        loader = PromptLoader(PROMPTS_DIR)
        result = loader.load(name)
        assert isinstance(result.metadata.supported_models, list)
        assert len(result.metadata.supported_models) >= 1

    @pytest.mark.parametrize("name", ALL_PROMPT_NAMES)
    def test_variables_is_list(self, name):
        loader = PromptLoader(PROMPTS_DIR)
        result = loader.load(name)
        assert isinstance(result.metadata.variables, list)

    @pytest.mark.parametrize("name", ALL_PROMPT_NAMES)
    def test_template_body_is_not_empty(self, name):
        loader = PromptLoader(PROMPTS_DIR)
        result = loader.load(name)
        assert len(result.template.strip()) > 50

    @pytest.mark.parametrize("name", ALL_PROMPT_NAMES)
    def test_template_does_not_contain_frontmatter(self, name):
        loader = PromptLoader(PROMPTS_DIR)
        result = loader.load(name)
        # Body should not start with --- (frontmatter stripped)
        assert not result.template.strip().startswith("---")

    def test_daily_report_expects_markdown_output(self):
        loader = PromptLoader(PROMPTS_DIR)
        result = loader.load("daily_report")
        assert result.metadata.expected_output == "markdown"

    def test_customer_update_expects_email_output(self):
        loader = PromptLoader(PROMPTS_DIR)
        result = loader.load("customer_update")
        assert result.metadata.expected_output == "email"

    def test_last_updated_is_set(self):
        loader = PromptLoader(PROMPTS_DIR)
        for name in ALL_PROMPT_NAMES:
            result = loader.load(name)
            assert result.metadata.last_updated != ""


# ── Caching ────────────────────────────────────────────────────────────────────

class TestCaching:
    def test_same_object_returned_on_second_load(self):
        loader = PromptLoader(PROMPTS_DIR)
        first = loader.load("daily_report")
        second = loader.load("daily_report")
        assert first is second  # same object from cache

    def test_clear_cache_forces_reload(self):
        loader = PromptLoader(PROMPTS_DIR)
        first = loader.load("daily_report")
        loader.clear_cache()
        second = loader.load("daily_report")
        assert first is not second  # new object after cache cleared
        assert first.metadata.version == second.metadata.version  # same content


# ── Error handling ─────────────────────────────────────────────────────────────

class TestErrorHandling:
    def test_missing_prompt_raises_file_not_found(self):
        loader = PromptLoader(PROMPTS_DIR)
        with pytest.raises(FileNotFoundError, match="not found"):
            loader.load("nonexistent_prompt")

    def test_error_message_includes_available_prompts(self):
        loader = PromptLoader(PROMPTS_DIR)
        with pytest.raises(FileNotFoundError) as exc_info:
            loader.load("nonexistent_prompt")
        assert "daily_report" in str(exc_info.value)


# ── Frontmatter parser (via tmp files) ────────────────────────────────────────

class TestFrontmatterParser:
    def test_scalar_values_parsed(self, tmp_path):
        (tmp_path / "test.md").write_text(
            "---\nname: test_prompt\nversion: 2.1.0\ndescription: A test prompt\nexpected_output: markdown\nlast_updated: 2026-07-08\n---\n\nPrompt body here.",
            encoding="utf-8",
        )
        loader = PromptLoader(tmp_path)
        result = loader.load("test")
        assert result.metadata.name == "test_prompt"
        assert result.metadata.version == "2.1.0"
        assert result.metadata.description == "A test prompt"
        assert result.metadata.expected_output == "markdown"
        assert result.template == "Prompt body here."

    def test_list_values_parsed(self, tmp_path):
        (tmp_path / "test.md").write_text(
            "---\nname: test\nversion: 1.0.0\nsupported_models:\n  - llama-3.3-70b-versatile\n  - mixtral-8x7b\nvariables:\n  - log_date\n  - stage\n---\n\nBody.",
            encoding="utf-8",
        )
        loader = PromptLoader(tmp_path)
        result = loader.load("test")
        assert "llama-3.3-70b-versatile" in result.metadata.supported_models
        assert "mixtral-8x7b" in result.metadata.supported_models
        assert "log_date" in result.metadata.variables
        assert "stage" in result.metadata.variables

    def test_body_without_frontmatter(self, tmp_path):
        (tmp_path / "bare.md").write_text(
            "You are a construction manager. Generate a report.",
            encoding="utf-8",
        )
        loader = PromptLoader(tmp_path)
        result = loader.load("bare")
        assert result.metadata.name == "bare"
        assert result.metadata.version == "0.0.0"
        assert "Generate a report" in result.template

    def test_unclosed_frontmatter_treated_as_body(self, tmp_path):
        (tmp_path / "bad.md").write_text(
            "---\nname: broken\n\nBody starts here.",
            encoding="utf-8",
        )
        loader = PromptLoader(tmp_path)
        result = loader.load("bad")
        # No closing --- means the whole thing is treated as the body
        assert result.metadata.name == "bad"

    def test_multiline_body_preserved(self, tmp_path):
        body = "Line 1.\nLine 2.\n\nLine 4 after blank."
        (tmp_path / "multi.md").write_text(
            f"---\nname: multi\nversion: 1.0.0\n---\n\n{body}",
            encoding="utf-8",
        )
        loader = PromptLoader(tmp_path)
        result = loader.load("multi")
        assert "Line 1." in result.template
        assert "Line 4 after blank." in result.template
