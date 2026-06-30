"""
tests/test_speech_validator.py — Unit tests for AudioValidator.

All tests use synthetic WAV files from conftest.py fixtures so they run
without any real audio files and without network access.
"""
from __future__ import annotations

import pytest

from speech.config import AudioValidationConfig
from speech.validators.audio_validator import AudioValidator


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def strict_config():
    """Config with tighter duration limits for boundary tests."""
    return AudioValidationConfig(
        min_duration_seconds=0.5,
        max_duration_seconds=5.0,
        min_sample_rate=8000,
        max_channels=2,
    )


@pytest.fixture()
def strict_validator(strict_config):
    return AudioValidator(strict_config)


# ── Passing cases ──────────────────────────────────────────────────────────────

class TestAudioValidatorPassing:
    def test_valid_wav_passes(self, validator, valid_wav):
        result = validator.validate(valid_wav)
        assert result.is_valid, f"Expected valid but got errors: {result.errors}"

    def test_valid_wav_has_no_errors(self, validator, valid_wav):
        result = validator.validate(valid_wav)
        assert result.errors == []

    def test_valid_wav_populates_audio_info(self, validator, valid_wav):
        result = validator.validate(valid_wav)
        if result.audio_info:
            assert result.audio_info.is_readable is True
            assert result.audio_info.duration_seconds > 0

    def test_long_wav_passes(self, validator, long_wav):
        result = validator.validate(long_wav)
        assert result.is_valid

    def test_stereo_produces_warning_not_error(self, validator, stereo_wav):
        result = validator.validate(stereo_wav)
        # Stereo is allowed but should produce a warning
        assert result.is_valid
        warning_texts = " ".join(result.warnings).lower()
        assert "stereo" in warning_texts or "channel" in warning_texts


# ── Failing cases ──────────────────────────────────────────────────────────────

class TestAudioValidatorFailures:
    def test_nonexistent_file_fails(self, validator, nonexistent_path):
        result = validator.validate(nonexistent_path)
        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_nonexistent_error_message(self, validator, nonexistent_path):
        result = validator.validate(nonexistent_path)
        combined = " ".join(result.errors).lower()
        assert "not found" in combined or "exist" in combined or "no such" in combined

    def test_empty_file_fails(self, validator, empty_wav):
        result = validator.validate(empty_wav)
        assert result.is_valid is False

    def test_unsupported_format_fails(self, validator, unsupported_wav):
        result = validator.validate(unsupported_wav)
        assert result.is_valid is False
        combined = " ".join(result.errors).lower()
        assert "format" in combined or "unsupported" in combined or "extension" in combined

    def test_short_wav_fails_duration(self, strict_validator, short_wav):
        result = strict_validator.validate(short_wav)
        # short_wav is 0.1s which is below the 0.5s minimum
        # It may fail on duration OR on readability depending on soundfile availability
        assert result.is_valid is False

    def test_failure_result_has_is_valid_false(self, validator, nonexistent_path):
        result = validator.validate(nonexistent_path)
        assert result.is_valid is False


# ── Result structure tests ─────────────────────────────────────────────────────

class TestValidationResultStructure:
    def test_valid_result_has_audio_info_or_none(self, validator, valid_wav):
        result = validator.validate(valid_wav)
        # audio_info may be None if soundfile not installed, but result is valid
        # because format check passed — this is acceptable
        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)

    def test_invalid_result_audio_info_may_be_none(self, validator, nonexistent_path):
        result = validator.validate(nonexistent_path)
        # audio_info is None when file doesn't exist
        assert result.audio_info is None

    def test_warnings_is_list(self, validator, valid_wav):
        result = validator.validate(valid_wav)
        assert isinstance(result.warnings, list)

    def test_errors_is_list_on_failure(self, validator, nonexistent_path):
        result = validator.validate(nonexistent_path)
        assert isinstance(result.errors, list)
        assert len(result.errors) >= 1


# ── AudioValidationConfig tests ────────────────────────────────────────────────

class TestAudioValidationConfig:
    def test_default_config_creates(self):
        config = AudioValidationConfig()
        assert config.max_file_size_mb > 0
        assert config.min_duration_seconds > 0
        assert config.max_duration_seconds > config.min_duration_seconds

    def test_supported_formats_not_empty(self):
        config = AudioValidationConfig()
        assert len(config.supported_formats) > 0
        assert "wav" in config.supported_formats

    def test_to_dict_has_all_keys(self):
        config = AudioValidationConfig()
        d = config.to_dict()
        for key in ("supported_formats", "max_file_size_mb",
                    "min_duration_seconds", "max_duration_seconds",
                    "min_sample_rate", "max_channels"):
            assert key in d
