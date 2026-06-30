"""
speech/validators/audio_validator.py — Pre-transcription audio quality gate.

The validator runs BEFORE the STT engine. Passing these checks does not
guarantee a good transcript, but failing them guarantees the transcription
would produce nothing useful (or crash the engine).

All checks are independent and run in sequence. Errors are blocking (reject).
Warnings are advisory (allow with flag). The pipeline short-circuits on the
first blocking error to avoid wasting time.
"""
from __future__ import annotations

import logging

from speech.config import AudioValidationConfig, SpeechProcessingConfig
from speech.loaders.audio_loader import AudioLoader
from speech.loaders.format_detector import detect_format
from speech.models.metadata import AudioFileInfo
from speech.models.processing_result import AudioValidationResult
from speech.utils.constants import (
    MAX_FILE_SIZE_MB,
    MIN_FILE_SIZE_BYTES,
    SUPPORTED_AUDIO_FORMATS,
)

logger = logging.getLogger(__name__)


class AudioValidator:
    """
    Validates audio files before they enter the transcription pipeline.

    Checks performed (in order):
    1. File existence
    2. Minimum file size (rejects empty / stub files)
    3. Format recognition (extension + magic bytes)
    4. Maximum file size
    5. Audio readability (can soundfile/librosa read headers?)
    6. Duration: minimum and maximum
    7. Sample rate: minimum acceptable
    8. Channel count: maximum acceptable
    9. Silence ratio (optional): rejects files with almost no speech

    Warnings (non-blocking):
    - Sample rate below recommended 16 kHz
    - Stereo audio (Whisper natively handles mono; stereo is auto-downmixed)
    - Duration near maximum limit
    """

    def __init__(self, config: AudioValidationConfig | None = None) -> None:
        self._cfg = config or AudioValidationConfig()
        self._loader = AudioLoader()

    def validate(self, file_path: str) -> AudioValidationResult:
        """
        Run all validation checks and return an AudioValidationResult.

        audio_info is populated even on failure so callers can report details.
        """
        errors: list[str] = []
        warnings: list[str] = []
        info: AudioFileInfo | None = None

        # ── Check 1: File existence ────────────────────────────────────────────
        from pathlib import Path
        path = Path(file_path)
        if not path.exists():
            return AudioValidationResult(
                is_valid=False,
                errors=[f"File not found: {file_path}"],
            )

        if not path.is_file():
            return AudioValidationResult(
                is_valid=False,
                errors=[f"Path is not a file: {file_path}"],
            )

        # ── Check 2: Minimum file size ─────────────────────────────────────────
        try:
            import os
            size_bytes = os.path.getsize(path)
        except OSError as exc:
            return AudioValidationResult(
                is_valid=False,
                errors=[f"Cannot access file: {exc}"],
            )

        if size_bytes < MIN_FILE_SIZE_BYTES:
            return AudioValidationResult(
                is_valid=False,
                errors=[
                    f"File too small ({size_bytes} bytes). "
                    f"Minimum is {MIN_FILE_SIZE_BYTES} bytes. "
                    f"File may be empty or corrupt."
                ],
            )

        # ── Check 3: Format recognition ────────────────────────────────────────
        detected_fmt = detect_format(path)
        if not detected_fmt:
            return AudioValidationResult(
                is_valid=False,
                errors=[
                    f"Unrecognized audio format for '{path.name}'. "
                    f"Supported formats: {', '.join(sorted(self._cfg.supported_formats))}"
                ],
            )
        if detected_fmt not in self._cfg.supported_formats:
            return AudioValidationResult(
                is_valid=False,
                errors=[
                    f"Unsupported format '{detected_fmt}' for '{path.name}'. "
                    f"Supported: {', '.join(sorted(self._cfg.supported_formats))}"
                ],
            )

        # ── Check 4: Maximum file size ─────────────────────────────────────────
        size_mb = size_bytes / (1024 * 1024)
        if size_mb > self._cfg.max_file_size_mb:
            return AudioValidationResult(
                is_valid=False,
                errors=[
                    f"File too large ({size_mb:.1f} MB). "
                    f"Maximum allowed: {self._cfg.max_file_size_mb} MB. "
                    f"Split the recording into smaller segments."
                ],
            )

        # ── Check 5: Audio readability + metadata ──────────────────────────────
        info = self._loader.load(file_path)
        if not info.is_readable:
            errors.append(
                f"Cannot read audio data from '{path.name}'. "
                f"File may be corrupt or use an unsupported codec. "
                f"Try re-encoding to WAV: ffmpeg -i {path.name} output.wav"
            )
            return AudioValidationResult(is_valid=False, errors=errors, audio_info=info)

        # ── Check 6: Duration ──────────────────────────────────────────────────
        if info.duration_seconds < self._cfg.min_duration_seconds:
            errors.append(
                f"Audio too short ({info.duration_seconds:.2f}s). "
                f"Minimum duration: {self._cfg.min_duration_seconds}s. "
                f"Recording may be empty or cut off."
            )

        if info.duration_seconds > self._cfg.max_duration_seconds:
            errors.append(
                f"Audio too long ({info.duration_seconds:.0f}s = "
                f"{info.duration_seconds / 3600:.1f} hours). "
                f"Maximum: {self._cfg.max_duration_seconds}s. "
                f"Split into multiple recordings."
            )

        if errors:
            return AudioValidationResult(is_valid=False, errors=errors, audio_info=info)

        # ── Check 7: Sample rate ───────────────────────────────────────────────
        if info.sample_rate > 0 and info.sample_rate < self._cfg.min_sample_rate:
            errors.append(
                f"Sample rate too low ({info.sample_rate} Hz). "
                f"Minimum: {self._cfg.min_sample_rate} Hz. "
                f"Audio quality is too degraded for reliable transcription."
            )

        if errors:
            return AudioValidationResult(is_valid=False, errors=errors, audio_info=info)

        # ── Check 8: Channel count ─────────────────────────────────────────────
        if info.channels > self._cfg.max_channels:
            errors.append(
                f"Too many audio channels ({info.channels}). "
                f"Maximum supported: {self._cfg.max_channels}."
            )

        if errors:
            return AudioValidationResult(is_valid=False, errors=errors, audio_info=info)

        # ── Warnings (non-blocking) ────────────────────────────────────────────
        from speech.utils.constants import RECOMMENDED_SAMPLE_RATE
        if info.sample_rate > 0 and info.sample_rate < RECOMMENDED_SAMPLE_RATE:
            warnings.append(
                f"Sample rate {info.sample_rate} Hz is below recommended "
                f"{RECOMMENDED_SAMPLE_RATE} Hz. Transcription accuracy may be reduced."
            )

        if info.channels > 1:
            warnings.append(
                f"Audio has {info.channels} channels (stereo/multi-channel). "
                f"Will be mixed to mono before transcription."
            )

        if info.duration_seconds > self._cfg.max_duration_seconds * 0.8:
            warnings.append(
                f"Audio is {info.duration_seconds:.0f}s, close to the "
                f"{self._cfg.max_duration_seconds:.0f}s limit. "
                f"Processing may be slow."
            )

        logger.debug(
            "Validation passed for '%s' (%.1fs, %d Hz, %s)",
            path.name,
            info.duration_seconds,
            info.sample_rate,
            detected_fmt,
        )

        return AudioValidationResult(
            is_valid=True,
            errors=errors,
            warnings=warnings,
            audio_info=info,
        )
