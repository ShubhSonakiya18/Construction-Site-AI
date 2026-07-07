"""
test_extraction_config.py — Tests for ExtractionConfig and GroqConfig.
"""
import os
import pytest

from extraction.config import ExtractionConfig, GroqConfig


class TestGroqConfig:
    def test_defaults(self):
        cfg = GroqConfig()
        assert cfg.model == "llama-3.3-70b-versatile"
        assert cfg.api_key == ""
        assert cfg.temperature == 0.1
        assert cfg.timeout_seconds == 60
        assert cfg.max_tokens == 4096

    def test_custom_values(self):
        cfg = GroqConfig(model="mixtral-8x7b-32768", temperature=0.5, timeout_seconds=30)
        assert cfg.model == "mixtral-8x7b-32768"
        assert cfg.temperature == 0.5
        assert cfg.timeout_seconds == 30


class TestExtractionConfig:
    def test_defaults(self):
        cfg = ExtractionConfig()
        assert cfg.provider == "groq"
        assert cfg.max_retries == 3
        assert cfg.retry_delay_seconds == 2.0
        assert cfg.retry_backoff == 2.0
        assert cfg.knowledge_dir == "knowledge"
        assert isinstance(cfg.groq, GroqConfig)

    def test_from_env_defaults(self):
        for var in [
            "EXTRACTION_PROVIDER",
            "EXTRACTION_GROQ_MODEL",
            "EXTRACTION_GROQ_TEMPERATURE",
            "EXTRACTION_GROQ_TIMEOUT",
            "EXTRACTION_MAX_RETRIES",
            "EXTRACTION_KNOWLEDGE_DIR",
        ]:
            os.environ.pop(var, None)

        cfg = ExtractionConfig.from_env()
        assert cfg.provider == "groq"
        assert cfg.groq.model == "llama-3.3-70b-versatile"
        assert cfg.groq.temperature == 0.1
        assert cfg.groq.timeout_seconds == 60
        assert cfg.max_retries == 3
        assert cfg.knowledge_dir == "knowledge"

    def test_from_env_reads_env_vars(self, monkeypatch):
        monkeypatch.setenv("EXTRACTION_PROVIDER", "groq")
        monkeypatch.setenv("EXTRACTION_GROQ_MODEL", "mixtral-8x7b-32768")
        monkeypatch.setenv("EXTRACTION_GROQ_TEMPERATURE", "0.3")
        monkeypatch.setenv("EXTRACTION_GROQ_TIMEOUT", "30")
        monkeypatch.setenv("EXTRACTION_MAX_RETRIES", "5")
        monkeypatch.setenv("EXTRACTION_KNOWLEDGE_DIR", "/data/knowledge")

        cfg = ExtractionConfig.from_env()
        assert cfg.provider == "groq"
        assert cfg.groq.model == "mixtral-8x7b-32768"
        assert cfg.groq.temperature == 0.3
        assert cfg.groq.timeout_seconds == 30
        assert cfg.max_retries == 5
        assert cfg.knowledge_dir == "/data/knowledge"

    def test_from_env_partial_override(self, monkeypatch):
        monkeypatch.setenv("EXTRACTION_GROQ_MODEL", "llama-3.1-8b-instant")
        cfg = ExtractionConfig.from_env()
        assert cfg.groq.model == "llama-3.1-8b-instant"
        assert cfg.groq.temperature == 0.1  # still default

    def test_groq_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key")
        cfg = ExtractionConfig.from_env()
        assert cfg.groq.api_key == "gsk_test_key"
