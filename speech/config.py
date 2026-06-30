"""
speech/config.py — Single source of truth for all speech processing settings.

Design rules (same as dataset_generation_framework/config.py):
- Every tunable value lives here. Zero magic numbers elsewhere.
- Config is a dataclass, not module-level constants, so it can be instantiated
  with overrides for tests without patching global state.
- from_env() reads environment variables so Docker/CI/CD can override without
  editing files.
- The Whisper model size is the most impactful knob: swap "base" -> "large-v3"
  for production without changing any other code.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from speech.utils.constants import (
    DEFAULT_BEAM_SIZE,
    DEFAULT_CHUNK_LENGTH_SECONDS,
    DEFAULT_CHUNK_OVERLAP_SECONDS,
    DEFAULT_COMPUTE_TYPE,
    DEFAULT_DEVICE,
    DEFAULT_LANGUAGE,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BACKOFF,
    DEFAULT_RETRY_DELAY_SECONDS,
    DEFAULT_TASK,
    DEFAULT_WHISPER_MODEL,
    LOW_CONFIDENCE_WARNING,
    MAX_CHANNELS,
    MAX_DURATION_SECONDS,
    MAX_FILE_SIZE_MB,
    MIN_DURATION_SECONDS,
    MIN_SAMPLE_RATE,
    RECOMMENDED_SAMPLE_RATE,
    SUPPORTED_AUDIO_FORMATS,
)

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


@dataclass
class AudioValidationConfig:
    """Constraints applied before transcription starts."""
    supported_formats: frozenset[str] = field(
        default_factory=lambda: SUPPORTED_AUDIO_FORMATS
    )
    max_file_size_mb: float = MAX_FILE_SIZE_MB
    min_duration_seconds: float = MIN_DURATION_SECONDS
    max_duration_seconds: float = MAX_DURATION_SECONDS
    min_sample_rate: int = MIN_SAMPLE_RATE
    max_channels: int = MAX_CHANNELS
    reject_silent_files: bool = True
    max_silence_ratio: float = 0.95

    def to_dict(self) -> dict:
        return {
            "supported_formats": sorted(self.supported_formats),
            "max_file_size_mb": self.max_file_size_mb,
            "min_duration_seconds": self.min_duration_seconds,
            "max_duration_seconds": self.max_duration_seconds,
            "min_sample_rate": self.min_sample_rate,
            "max_channels": self.max_channels,
            "reject_silent_files": self.reject_silent_files,
            "max_silence_ratio": self.max_silence_ratio,
        }


@dataclass
class WhisperConfig:
    """
    Configuration for the Faster Whisper STT engine.

    Changing model_size is the single biggest quality/speed trade-off:
        tiny   (75 MB)  — dev/testing only
        base   (150 MB) — acceptable for development
        small  (250 MB) — good balance
        medium (1.5 GB) — recommended for production
        large-v3 (3 GB) — best accuracy, requires GPU for real-time

    compute_type options:
        int8       — fastest, slightly lower accuracy (default for CPU)
        float16    — GPU only, good balance
        float32    — most accurate, most memory
    """
    model_size: str = DEFAULT_WHISPER_MODEL
    device: str = DEFAULT_DEVICE             # "cpu", "cuda", "auto"
    compute_type: str = DEFAULT_COMPUTE_TYPE
    language: str | None = DEFAULT_LANGUAGE  # None = auto-detect every file
    task: str = DEFAULT_TASK                 # "transcribe" | "translate"
    beam_size: int = DEFAULT_BEAM_SIZE
    vad_filter: bool = True                  # skip silent regions automatically
    word_timestamps: bool = True             # per-word timing for Sprint 4
    condition_on_previous_text: bool = True  # context-aware decoding
    # Path where models are downloaded and cached
    model_cache_dir: str = str(PROJECT_ROOT / "speech" / ".model_cache")

    def to_dict(self) -> dict:
        return {
            "model_size": self.model_size,
            "device": self.device,
            "compute_type": self.compute_type,
            "language": self.language,
            "task": self.task,
            "beam_size": self.beam_size,
            "vad_filter": self.vad_filter,
            "word_timestamps": self.word_timestamps,
            "condition_on_previous_text": self.condition_on_previous_text,
            "model_cache_dir": self.model_cache_dir,
        }


@dataclass
class PreprocessingConfig:
    """Audio transformations applied after validation, before transcription."""
    enable_normalization: bool = True        # volume normalization
    target_sample_rate: int = RECOMMENDED_SAMPLE_RATE  # 16 kHz for Whisper
    enable_noise_reduction: bool = False     # requires noisereduce package
    noise_reduction_strength: float = 0.75  # 0.0–1.0; only used if enabled
    # Chunking: Whisper handles it internally; these expose the config for reports
    chunk_length_seconds: float = DEFAULT_CHUNK_LENGTH_SECONDS
    chunk_overlap_seconds: float = DEFAULT_CHUNK_OVERLAP_SECONDS

    def to_dict(self) -> dict:
        return {
            "enable_normalization": self.enable_normalization,
            "target_sample_rate": self.target_sample_rate,
            "enable_noise_reduction": self.enable_noise_reduction,
            "noise_reduction_strength": self.noise_reduction_strength,
            "chunk_length_seconds": self.chunk_length_seconds,
            "chunk_overlap_seconds": self.chunk_overlap_seconds,
        }


@dataclass
class PostprocessingConfig:
    """Transformations applied to the raw transcript after STT."""
    clean_filler_words: bool = True
    normalize_construction_terms: bool = True
    min_segment_confidence: float = 0.0     # segments below this are flagged
    low_confidence_warning_threshold: float = LOW_CONFIDENCE_WARNING

    def to_dict(self) -> dict:
        return {
            "clean_filler_words": self.clean_filler_words,
            "normalize_construction_terms": self.normalize_construction_terms,
            "min_segment_confidence": self.min_segment_confidence,
            "low_confidence_warning_threshold": self.low_confidence_warning_threshold,
        }


@dataclass
class SpeechProcessingConfig:
    """
    Root configuration for the Speech Processing Framework.

    Instantiate with defaults for normal use:
        config = SpeechProcessingConfig()

    Override for production:
        config = SpeechProcessingConfig(
            whisper=WhisperConfig(model_size="large-v3", device="cuda"),
        )

    Override from environment:
        config = SpeechProcessingConfig.from_env()
    """
    validation: AudioValidationConfig = field(default_factory=AudioValidationConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    preprocessing: PreprocessingConfig = field(default_factory=PreprocessingConfig)
    postprocessing: PostprocessingConfig = field(default_factory=PostprocessingConfig)

    max_retries: int = DEFAULT_MAX_RETRIES
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS
    retry_backoff: float = DEFAULT_RETRY_BACKOFF

    # Progress callback: called with (stage_name: str, progress_pct: float)
    # None = no progress reporting. Sprint 7 API will inject a WebSocket emitter here.
    progress_callback: object = None   # Callable[[str, float], None] | None

    def to_dict(self) -> dict:
        return {
            "validation": self.validation.to_dict(),
            "whisper": self.whisper.to_dict(),
            "preprocessing": self.preprocessing.to_dict(),
            "postprocessing": self.postprocessing.to_dict(),
            "max_retries": self.max_retries,
            "retry_delay_seconds": self.retry_delay_seconds,
            "retry_backoff": self.retry_backoff,
        }

    @classmethod
    def from_env(cls) -> "SpeechProcessingConfig":
        """
        Build config from environment variables.

        Environment variables (all optional — defaults used if not set):
            SPEECH_WHISPER_MODEL_SIZE    = tiny|base|small|medium|large-v3
            SPEECH_WHISPER_DEVICE        = cpu|cuda|auto
            SPEECH_WHISPER_COMPUTE_TYPE  = int8|float16|float32
            SPEECH_WHISPER_LANGUAGE      = en  (empty = auto-detect)
            SPEECH_MAX_FILE_SIZE_MB      = 500
            SPEECH_MAX_DURATION_SECONDS  = 7200
            SPEECH_ENABLE_NOISE_REDUCTION = true|false
            SPEECH_MODELS_DIR            = /path/to/model/cache
        """
        def _env_bool(key: str, default: bool) -> bool:
            val = os.environ.get(key, "").lower()
            if val in ("true", "1", "yes"):
                return True
            if val in ("false", "0", "no"):
                return False
            return default

        def _env_float(key: str, default: float) -> float:
            try:
                return float(os.environ.get(key, default))
            except (ValueError, TypeError):
                return default

        def _env_int(key: str, default: int) -> int:
            try:
                return int(os.environ.get(key, default))
            except (ValueError, TypeError):
                return default

        lang = os.environ.get("SPEECH_WHISPER_LANGUAGE", "")
        model_cache = os.environ.get(
            "SPEECH_MODELS_DIR",
            str(PROJECT_ROOT / "speech" / ".model_cache"),
        )

        return cls(
            validation=AudioValidationConfig(
                max_file_size_mb=_env_float("SPEECH_MAX_FILE_SIZE_MB", MAX_FILE_SIZE_MB),
                max_duration_seconds=_env_float(
                    "SPEECH_MAX_DURATION_SECONDS", MAX_DURATION_SECONDS
                ),
            ),
            whisper=WhisperConfig(
                model_size=os.environ.get("SPEECH_WHISPER_MODEL_SIZE", DEFAULT_WHISPER_MODEL),
                device=os.environ.get("SPEECH_WHISPER_DEVICE", DEFAULT_DEVICE),
                compute_type=os.environ.get("SPEECH_WHISPER_COMPUTE_TYPE", DEFAULT_COMPUTE_TYPE),
                language=lang if lang else None,
                model_cache_dir=model_cache,
            ),
            preprocessing=PreprocessingConfig(
                enable_noise_reduction=_env_bool(
                    "SPEECH_ENABLE_NOISE_REDUCTION", False
                ),
            ),
            max_retries=_env_int("SPEECH_MAX_RETRIES", DEFAULT_MAX_RETRIES),
        )
