"""
tests/test_generation_config.py — Unit tests for GenerationConfig and GenerationGroqConfig.

Tests cover: defaults, from_env() overrides, attribute structure compatibility
with EngineFactory duck typing. No LLM calls, no file I/O.
"""
from __future__ import annotations

import os

import pytest

from generation.config import GenerationConfig, GenerationGroqConfig


class TestGenerationGroqConfig:
    def test_defaults(self):
        cfg = GenerationGroqConfig()
        assert cfg.model == "llama-3.3-70b-versatile"
        assert cfg.api_key == ""
        assert cfg.temperature == 0.3
        assert cfg.timeout_seconds == 90
        assert cfg.max_tokens == 2048

    def test_temperature_higher_than_extraction(self):
        # Generation uses 0.3 (creative prose); extraction uses 0.1 (deterministic JSON)
        cfg = GenerationGroqConfig()
        assert cfg.temperature > 0.1

    def test_custom_values(self):
        cfg = GenerationGroqConfig(
            model="mixtral-8x7b",
            api_key="gsk_test",
            temperature=0.5,
            timeout_seconds=120,
            max_tokens=4096,
        )
        assert cfg.model == "mixtral-8x7b"
        assert cfg.api_key == "gsk_test"
        assert cfg.temperature == 0.5
        assert cfg.timeout_seconds == 120
        assert cfg.max_tokens == 4096


class TestGenerationConfig:
    def test_defaults(self):
        cfg = GenerationConfig()
        assert cfg.provider == "groq"
        assert cfg.max_retries == 3
        assert cfg.retry_delay_seconds == 2.0
        assert cfg.retry_backoff == 2.0
        assert cfg.prompts_dir == "generation/prompts"
        assert isinstance(cfg.groq, GenerationGroqConfig)

    def test_groq_nested_config_default(self):
        cfg = GenerationConfig()
        assert cfg.groq.model == "llama-3.3-70b-versatile"
        assert cfg.groq.temperature == 0.3

    def test_from_env_reads_provider(self, monkeypatch):
        monkeypatch.setenv("GENERATION_PROVIDER", "ollama")
        cfg = GenerationConfig.from_env()
        assert cfg.provider == "ollama"

    def test_from_env_reads_groq_model(self, monkeypatch):
        monkeypatch.setenv("GENERATION_GROQ_MODEL", "mixtral-8x7b")
        cfg = GenerationConfig.from_env()
        assert cfg.groq.model == "mixtral-8x7b"

    def test_from_env_reads_api_key(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key")
        cfg = GenerationConfig.from_env()
        assert cfg.groq.api_key == "gsk_test_key"

    def test_from_env_reads_temperature(self, monkeypatch):
        monkeypatch.setenv("GENERATION_GROQ_TEMPERATURE", "0.7")
        cfg = GenerationConfig.from_env()
        assert cfg.groq.temperature == pytest.approx(0.7)

    def test_from_env_reads_timeout(self, monkeypatch):
        monkeypatch.setenv("GENERATION_GROQ_TIMEOUT", "120")
        cfg = GenerationConfig.from_env()
        assert cfg.groq.timeout_seconds == 120

    def test_from_env_reads_max_tokens(self, monkeypatch):
        monkeypatch.setenv("GENERATION_GROQ_MAX_TOKENS", "4096")
        cfg = GenerationConfig.from_env()
        assert cfg.groq.max_tokens == 4096

    def test_from_env_reads_max_retries(self, monkeypatch):
        monkeypatch.setenv("GENERATION_MAX_RETRIES", "5")
        cfg = GenerationConfig.from_env()
        assert cfg.max_retries == 5

    def test_from_env_uses_defaults_without_env_vars(self, monkeypatch):
        for key in [
            "GENERATION_PROVIDER", "GENERATION_GROQ_MODEL",
            "GENERATION_GROQ_TEMPERATURE", "GENERATION_GROQ_TIMEOUT",
            "GENERATION_MAX_RETRIES", "GROQ_API_KEY",
        ]:
            monkeypatch.delenv(key, raising=False)
        cfg = GenerationConfig.from_env()
        assert cfg.provider == "groq"
        assert cfg.groq.model == "llama-3.3-70b-versatile"
        assert cfg.max_retries == 3

    def test_duck_typing_compatibility_with_engine_factory(self):
        """
        EngineFactory.create_from_config() accesses:
            config.provider
            config.groq.model
            config.groq.api_key
            config.groq.temperature
            config.groq.timeout_seconds
        Verify all these attributes exist on GenerationConfig.
        """
        cfg = GenerationConfig()
        assert hasattr(cfg, "provider")
        assert hasattr(cfg.groq, "model")
        assert hasattr(cfg.groq, "api_key")
        assert hasattr(cfg.groq, "temperature")
        assert hasattr(cfg.groq, "timeout_seconds")

    def test_independent_groq_configs_per_instance(self):
        """Each GenerationConfig gets its own GenerationGroqConfig (not shared)."""
        cfg1 = GenerationConfig()
        cfg2 = GenerationConfig()
        cfg1.groq.api_key = "key1"
        assert cfg2.groq.api_key == ""
