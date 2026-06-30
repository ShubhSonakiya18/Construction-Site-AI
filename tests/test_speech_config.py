"""
tests/test_speech_config.py — Unit tests for SpeechProcessingConfig.

Tests cover default construction, env-var overrides (via monkeypatch),
and nested sub-config serialization.
"""
from __future__ import annotations

import pytest

from speech.config import (
    AudioValidationConfig,
    PostprocessingConfig,
    PreprocessingConfig,
    SpeechProcessingConfig,
    WhisperConfig,
)
from speech.utils.constants import (
    DEFAULT_COMPUTE_TYPE,
    DEFAULT_DEVICE,
    DEFAULT_WHISPER_MODEL,
    MAX_DURATION_SECONDS,
    MAX_FILE_SIZE_MB,
    RECOMMENDED_SAMPLE_RATE,
    SUPPORTED_AUDIO_FORMATS,
)


# ── Default construction ───────────────────────────────────────────────────────

class TestDefaultConfig:
    def test_creates_with_no_args(self):
        config = SpeechProcessingConfig()
        assert config is not None

    def test_default_whisper_model(self):
        config = SpeechProcessingConfig()
        assert config.whisper.model_size == DEFAULT_WHISPER_MODEL

    def test_default_device(self):
        config = SpeechProcessingConfig()
        assert config.whisper.device == DEFAULT_DEVICE

    def test_default_compute_type(self):
        config = SpeechProcessingConfig()
        assert config.whisper.compute_type == DEFAULT_COMPUTE_TYPE

    def test_default_max_file_size(self):
        config = SpeechProcessingConfig()
        assert config.validation.max_file_size_mb == MAX_FILE_SIZE_MB

    def test_default_max_duration(self):
        config = SpeechProcessingConfig()
        assert config.validation.max_duration_seconds == MAX_DURATION_SECONDS

    def test_default_vad_filter_on(self):
        config = SpeechProcessingConfig()
        assert config.whisper.vad_filter is True

    def test_default_word_timestamps_on(self):
        config = SpeechProcessingConfig()
        assert config.whisper.word_timestamps is True

    def test_default_noise_reduction_off(self):
        config = SpeechProcessingConfig()
        assert config.preprocessing.enable_noise_reduction is False

    def test_default_filler_removal_on(self):
        config = SpeechProcessingConfig()
        assert config.postprocessing.clean_filler_words is True

    def test_default_construction_norm_on(self):
        config = SpeechProcessingConfig()
        assert config.postprocessing.normalize_construction_terms is True

    def test_supported_formats_not_empty(self):
        config = SpeechProcessingConfig()
        assert len(config.validation.supported_formats) > 0
        assert "wav" in config.validation.supported_formats


# ── Override via constructor ───────────────────────────────────────────────────

class TestConfigOverride:
    def test_whisper_model_override(self):
        config = SpeechProcessingConfig(
            whisper=WhisperConfig(model_size="large-v3")
        )
        assert config.whisper.model_size == "large-v3"

    def test_device_override(self):
        config = SpeechProcessingConfig(
            whisper=WhisperConfig(device="cuda")
        )
        assert config.whisper.device == "cuda"

    def test_validation_override(self):
        config = SpeechProcessingConfig(
            validation=AudioValidationConfig(max_file_size_mb=100.0)
        )
        assert config.validation.max_file_size_mb == 100.0

    def test_noise_reduction_override(self):
        config = SpeechProcessingConfig(
            preprocessing=PreprocessingConfig(enable_noise_reduction=True)
        )
        assert config.preprocessing.enable_noise_reduction is True

    def test_progress_callback_default_none(self):
        config = SpeechProcessingConfig()
        assert config.progress_callback is None

    def test_progress_callback_can_be_set(self):
        calls = []
        def cb(stage, pct):
            calls.append((stage, pct))
        config = SpeechProcessingConfig(progress_callback=cb)
        assert config.progress_callback is cb


# ── from_env() ─────────────────────────────────────────────────────────────────

class TestFromEnv:
    def test_from_env_creates_config(self):
        config = SpeechProcessingConfig.from_env()
        assert isinstance(config, SpeechProcessingConfig)

    def test_from_env_reads_model_size(self, monkeypatch):
        monkeypatch.setenv("SPEECH_WHISPER_MODEL_SIZE", "small")
        config = SpeechProcessingConfig.from_env()
        assert config.whisper.model_size == "small"

    def test_from_env_reads_device(self, monkeypatch):
        monkeypatch.setenv("SPEECH_WHISPER_DEVICE", "auto")
        config = SpeechProcessingConfig.from_env()
        assert config.whisper.device == "auto"

    def test_from_env_reads_compute_type(self, monkeypatch):
        monkeypatch.setenv("SPEECH_WHISPER_COMPUTE_TYPE", "float32")
        config = SpeechProcessingConfig.from_env()
        assert config.whisper.compute_type == "float32"

    def test_from_env_reads_language(self, monkeypatch):
        monkeypatch.setenv("SPEECH_WHISPER_LANGUAGE", "en")
        config = SpeechProcessingConfig.from_env()
        assert config.whisper.language == "en"

    def test_from_env_empty_language_is_none(self, monkeypatch):
        monkeypatch.setenv("SPEECH_WHISPER_LANGUAGE", "")
        config = SpeechProcessingConfig.from_env()
        assert config.whisper.language is None

    def test_from_env_reads_noise_reduction_true(self, monkeypatch):
        monkeypatch.setenv("SPEECH_ENABLE_NOISE_REDUCTION", "true")
        config = SpeechProcessingConfig.from_env()
        assert config.preprocessing.enable_noise_reduction is True

    def test_from_env_reads_noise_reduction_false(self, monkeypatch):
        monkeypatch.setenv("SPEECH_ENABLE_NOISE_REDUCTION", "false")
        config = SpeechProcessingConfig.from_env()
        assert config.preprocessing.enable_noise_reduction is False

    def test_from_env_reads_max_file_size(self, monkeypatch):
        monkeypatch.setenv("SPEECH_MAX_FILE_SIZE_MB", "100.0")
        config = SpeechProcessingConfig.from_env()
        assert config.validation.max_file_size_mb == pytest.approx(100.0)

    def test_from_env_reads_max_duration(self, monkeypatch):
        monkeypatch.setenv("SPEECH_MAX_DURATION_SECONDS", "3600.0")
        config = SpeechProcessingConfig.from_env()
        assert config.validation.max_duration_seconds == pytest.approx(3600.0)

    def test_from_env_unset_uses_defaults(self, monkeypatch):
        for key in (
            "SPEECH_WHISPER_MODEL_SIZE", "SPEECH_WHISPER_DEVICE",
            "SPEECH_WHISPER_COMPUTE_TYPE", "SPEECH_WHISPER_LANGUAGE",
        ):
            monkeypatch.delenv(key, raising=False)
        config = SpeechProcessingConfig.from_env()
        assert config.whisper.model_size == DEFAULT_WHISPER_MODEL
        assert config.whisper.device == DEFAULT_DEVICE


# ── Serialization ──────────────────────────────────────────────────────────────

class TestConfigSerialization:
    def test_to_dict_has_top_level_keys(self):
        config = SpeechProcessingConfig()
        d = config.to_dict()
        for key in ("validation", "whisper", "preprocessing", "postprocessing",
                    "max_retries", "retry_delay_seconds", "retry_backoff"):
            assert key in d

    def test_validation_subdict(self):
        config = SpeechProcessingConfig()
        d = config.to_dict()
        assert "max_file_size_mb" in d["validation"]
        assert "supported_formats" in d["validation"]

    def test_whisper_subdict(self):
        config = SpeechProcessingConfig()
        d = config.to_dict()
        assert "model_size" in d["whisper"]
        assert "device" in d["whisper"]
        assert "vad_filter" in d["whisper"]

    def test_preprocessing_subdict(self):
        config = SpeechProcessingConfig()
        d = config.to_dict()
        assert "enable_normalization" in d["preprocessing"]
        assert "enable_noise_reduction" in d["preprocessing"]

    def test_postprocessing_subdict(self):
        config = SpeechProcessingConfig()
        d = config.to_dict()
        assert "clean_filler_words" in d["postprocessing"]
        assert "normalize_construction_terms" in d["postprocessing"]
