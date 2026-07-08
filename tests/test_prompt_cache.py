"""
tests/test_prompt_cache.py — Unit tests for Sprint 5.1 mtime-aware PromptLoader cache.

Tests cover:
  - Cache hit when file is unchanged (same object, no re-read)
  - Cache miss on first load
  - Automatic eviction when file mtime changes
  - clear_cache() clears both _cache and _mtime
  - Mtime dict is populated on load
  - Multiple prompts cached independently
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from generation.prompts.loader import PromptLoader

PROMPTS_DIR = Path("generation/prompts")


class TestMtimeAwareCache:
    def test_first_load_is_a_cache_miss(self, tmp_path):
        """First access reads from disk and stores mtime."""
        (tmp_path / "test.md").write_text(
            "---\nname: test\nversion: 1.0.0\n---\n\nBody.", encoding="utf-8"
        )
        loader = PromptLoader(tmp_path)
        assert "test" not in loader._cache
        assert "test" not in loader._mtime
        loader.load("test")
        assert "test" in loader._cache
        assert "test" in loader._mtime

    def test_second_load_same_file_returns_cached_object(self, tmp_path):
        """Unchanged file → same LoadedPrompt object from cache."""
        (tmp_path / "test.md").write_text(
            "---\nname: test\nversion: 1.0.0\n---\n\nBody.", encoding="utf-8"
        )
        loader = PromptLoader(tmp_path)
        first = loader.load("test")
        second = loader.load("test")
        assert first is second

    def test_mtime_stored_matches_actual_file_mtime(self, tmp_path):
        """The stored mtime matches the file's actual mtime."""
        path = tmp_path / "test.md"
        path.write_text("---\nname: test\nversion: 1.0.0\n---\n\nBody.", encoding="utf-8")
        loader = PromptLoader(tmp_path)
        loader.load("test")
        assert loader._mtime["test"] == os.path.getmtime(path)

    def test_modified_file_triggers_automatic_reload(self, tmp_path):
        """Editing a prompt file is detected on next load without restart."""
        path = tmp_path / "test.md"
        path.write_text("---\nname: test\nversion: 1.0.0\n---\n\nOriginal body.", encoding="utf-8")
        loader = PromptLoader(tmp_path)
        first = loader.load("test")
        assert "Original body" in first.template

        # Simulate file modification with a future mtime
        path.write_text("---\nname: test\nversion: 2.0.0\n---\n\nUpdated body.", encoding="utf-8")
        # Force mtime to differ (some filesystems have 1s mtime resolution)
        future = os.path.getmtime(path) + 1.0
        os.utime(path, (future, future))

        second = loader.load("test")
        assert second is not first
        assert second.metadata.version == "2.0.0"
        assert "Updated body" in second.template

    def test_unchanged_file_does_not_reload(self, tmp_path):
        """File with same mtime is never re-read from disk."""
        path = tmp_path / "test.md"
        path.write_text("---\nname: test\nversion: 1.0.0\n---\n\nBody.", encoding="utf-8")
        loader = PromptLoader(tmp_path)
        first = loader.load("test")
        # Load multiple times without touching the file
        for _ in range(5):
            result = loader.load("test")
            assert result is first

    def test_clear_cache_removes_both_cache_and_mtime(self, tmp_path):
        """clear_cache() clears _cache and _mtime together."""
        (tmp_path / "test.md").write_text(
            "---\nname: test\nversion: 1.0.0\n---\n\nBody.", encoding="utf-8"
        )
        loader = PromptLoader(tmp_path)
        loader.load("test")
        assert len(loader._cache) == 1
        assert len(loader._mtime) == 1

        loader.clear_cache()
        assert len(loader._cache) == 0
        assert len(loader._mtime) == 0

    def test_clear_cache_forces_reload(self, tmp_path):
        """After clear_cache(), the next load returns a new object."""
        (tmp_path / "test.md").write_text(
            "---\nname: test\nversion: 1.0.0\n---\n\nBody.", encoding="utf-8"
        )
        loader = PromptLoader(tmp_path)
        first = loader.load("test")
        loader.clear_cache()
        second = loader.load("test")
        assert first is not second
        assert first.metadata.version == second.metadata.version

    def test_multiple_prompts_cached_independently(self, tmp_path):
        """Cache for one prompt does not affect another."""
        (tmp_path / "a.md").write_text(
            "---\nname: a\nversion: 1.0.0\n---\n\nPrompt A.", encoding="utf-8"
        )
        (tmp_path / "b.md").write_text(
            "---\nname: b\nversion: 1.0.0\n---\n\nPrompt B.", encoding="utf-8"
        )
        loader = PromptLoader(tmp_path)
        a = loader.load("a")
        b = loader.load("b")
        assert "a" in loader._mtime
        assert "b" in loader._mtime
        assert loader.load("a") is a
        assert loader.load("b") is b


class TestRealPromptsCache:
    def test_real_prompts_are_cached_after_first_load(self):
        """Verify the real prompt files populate the mtime dict."""
        loader = PromptLoader(PROMPTS_DIR)
        for name in ["daily_report", "customer_update", "safety_talk", "material_reminder"]:
            loader.load(name)
        for name in ["daily_report", "customer_update", "safety_talk", "material_reminder"]:
            assert name in loader._mtime
            assert loader._mtime[name] > 0

    def test_real_prompts_cache_hit_on_second_load(self):
        """Repeated loads of real files return the same object."""
        loader = PromptLoader(PROMPTS_DIR)
        first = loader.load("daily_report")
        second = loader.load("daily_report")
        assert first is second
