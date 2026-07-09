"""
tests/conftest.py — Shared fixtures for the Speech Processing Framework test suite.

Synthetic audio is generated with numpy + soundfile so tests can run without
real recordings. The generator produces single-frequency sine-tone WAV files
at 16 kHz mono — valid audio that passes all AudioValidator checks.

Real-audio-dependent tests (WER acceptance tests) are gated with:
    @pytest.mark.skipif(not HAS_REAL_AUDIO, reason="real audio required")
"""
from __future__ import annotations

import os
import wave
from pathlib import Path

import pytest

# ── Optional dependency flags ──────────────────────────────────────────────────
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import soundfile  # noqa: F401
    HAS_SOUNDFILE = True
except ImportError:
    HAS_SOUNDFILE = False

REAL_AUDIO_DIR = Path(__file__).parent.parent / "data" / "sample_audio"
HAS_REAL_AUDIO = any(REAL_AUDIO_DIR.glob("*.wav")) if REAL_AUDIO_DIR.exists() else False


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_sine_wav(
    path: str,
    duration_seconds: float = 2.0,
    frequency_hz: float = 440.0,
    sample_rate: int = 16000,
) -> str:
    """
    Generate a sine-tone WAV file at the given path.

    Uses numpy if available (better quality) — falls back to stdlib wave
    (produces silence instead, but the WAV container is still valid).
    """
    num_samples = int(duration_seconds * sample_rate)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if HAS_NUMPY and HAS_SOUNDFILE:
        import soundfile as sf
        t = np.linspace(0, duration_seconds, num_samples, endpoint=False)
        audio = (np.sin(2 * np.pi * frequency_hz * t) * 0.5).astype(np.float32)
        sf.write(str(out), audio, sample_rate, subtype="PCM_16")
    else:
        with wave.open(str(out), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)          # 16-bit
            wf.setframerate(sample_rate)
            if HAS_NUMPY:
                t = np.linspace(0, duration_seconds, num_samples, endpoint=False)
                audio = (np.sin(2 * np.pi * frequency_hz * t) * 16383).astype(np.int16)
                wf.writeframes(audio.tobytes())
            else:
                # Silence fallback — still a valid WAV AudioValidator can read
                wf.writeframes(b"\x00" * num_samples * 2)

    return str(out.resolve())


def make_silent_wav(path: str, duration_seconds: float = 2.0,
                    sample_rate: int = 16000) -> str:
    """Generate a silent WAV file."""
    return make_sine_wav(path, duration_seconds=duration_seconds,
                         frequency_hz=0.0001, sample_rate=sample_rate)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def tmp_audio_dir(tmp_path_factory):
    """Session-scoped temp directory for generated test audio files."""
    return tmp_path_factory.mktemp("audio")


@pytest.fixture(scope="session")
def valid_wav(tmp_audio_dir):
    """A valid 2-second 16kHz mono WAV sine-tone."""
    path = str(tmp_audio_dir / "valid_2s.wav")
    return make_sine_wav(path, duration_seconds=2.0)


@pytest.fixture(scope="session")
def short_wav(tmp_audio_dir):
    """A WAV file shorter than MIN_DURATION_SECONDS (0.5s) — should fail validation."""
    path = str(tmp_audio_dir / "short_0_1s.wav")
    return make_sine_wav(path, duration_seconds=0.1)


@pytest.fixture(scope="session")
def long_wav(tmp_audio_dir):
    """A 10-second WAV file — useful for chunker tests."""
    path = str(tmp_audio_dir / "long_10s.wav")
    return make_sine_wav(path, duration_seconds=10.0)


@pytest.fixture(scope="session")
def stereo_wav(tmp_audio_dir):
    """A 2-second stereo WAV (2 channels) — should produce a warning."""
    num_samples = 32000
    p = tmp_audio_dir / "stereo_2s.wav"
    if HAS_NUMPY and HAS_SOUNDFILE:
        import soundfile as sf
        t = np.linspace(0, 2.0, num_samples, endpoint=False)
        audio = np.stack([
            (np.sin(2 * np.pi * 440.0 * t) * 0.5).astype(np.float32),
            (np.sin(2 * np.pi * 880.0 * t) * 0.5).astype(np.float32),
        ], axis=1)
        sf.write(str(p), audio, 16000, subtype="PCM_16")
    else:
        with wave.open(str(p), "w") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00" * num_samples * 2 * 2)
    return str(p.resolve())


@pytest.fixture()
def nonexistent_path():
    return "/nonexistent/path/audio.wav"


@pytest.fixture()
def empty_wav(tmp_path):
    """A zero-byte file — should fail min-size check."""
    p = tmp_path / "empty.wav"
    p.write_bytes(b"")
    return str(p)


@pytest.fixture()
def fake_wav(tmp_path):
    """A .wav file with wrong magic bytes (not a real WAV)."""
    p = tmp_path / "fake.wav"
    p.write_bytes(b"NOT_A_REAL_WAV_FILE_CONTENT")
    return str(p)


@pytest.fixture()
def unsupported_wav(tmp_path):
    """A file with an unsupported extension, large enough to pass the size check."""
    p = tmp_path / "audio.xyz"
    p.write_bytes(b"fake content " * 100)
    return str(p)


@pytest.fixture()
def default_config():
    """Default SpeechProcessingConfig (no env overrides)."""
    from speech.config import SpeechProcessingConfig
    return SpeechProcessingConfig()


@pytest.fixture()
def validation_config():
    """AudioValidationConfig with defaults."""
    from speech.config import AudioValidationConfig
    return AudioValidationConfig()


@pytest.fixture()
def validator(validation_config):
    """AudioValidator with default config."""
    from speech.validators.audio_validator import AudioValidator
    return AudioValidator(validation_config)


@pytest.fixture()
def sample_transcript():
    """A small synthetic Transcript object for postprocessor tests."""
    from speech.models.transcript import Transcript, TranscriptSegment, WordTimestamp
    segments = [
        TranscriptSegment(
            id=0,
            text="Um so we need to check the re bar on level two.",
            start=0.0,
            end=4.5,
            avg_logprob=-0.3,
            no_speech_prob=0.01,
            confidence=0.74,
            words=[
                WordTimestamp("Um", 0.0, 0.3, 0.5),
                WordTimestamp("so", 0.3, 0.6, 0.8),
                WordTimestamp("we", 0.6, 0.8, 0.9),
                WordTimestamp("need", 0.8, 1.1, 0.9),
                WordTimestamp("to", 1.1, 1.3, 0.95),
                WordTimestamp("check", 1.3, 1.8, 0.92),
                WordTimestamp("the", 1.8, 2.0, 0.88),
                WordTimestamp("re", 2.0, 2.4, 0.7),
                WordTimestamp("bar", 2.4, 2.8, 0.7),
                WordTimestamp("on", 2.8, 3.0, 0.9),
                WordTimestamp("level", 3.0, 3.4, 0.88),
                WordTimestamp("two", 3.4, 3.8, 0.91),
            ],
        ),
        TranscriptSegment(
            id=1,
            text="[INAUDIBLE]",
            start=4.5,
            end=5.0,
            avg_logprob=-5.0,
            no_speech_prob=0.95,
            confidence=0.01,
            words=[],
        ),
        TranscriptSegment(
            id=2,
            text="The h v a c unit needs uh replacement.",
            start=5.0,
            end=9.0,
            avg_logprob=-0.25,
            no_speech_prob=0.02,
            confidence=0.78,
            words=[],
        ),
    ]
    return Transcript(
        text=" ".join(s.text for s in segments),
        language="en",
        language_probability=0.99,
        duration_seconds=9.0,
        segments=segments,
    )


@pytest.fixture()
def sample_processing_result(sample_transcript):
    """A minimal SpeechProcessingResult for exporter tests."""
    from speech.models.metadata import AudioFileInfo, ProcessingStats, SpeechProcessingMetadata
    from speech.models.processing_result import AudioValidationResult, SpeechProcessingResult

    audio_info = AudioFileInfo(
        file_path="/fake/recording.wav",
        file_name="recording.wav",
        file_size_bytes=512000,
        format="wav",
        duration_seconds=9.0,
        sample_rate=16000,
        channels=1,
        bit_depth=16,
        codec=None,
        is_readable=True,
    )
    stats = ProcessingStats(
        started_at="2026-07-01T10:00:00+00:00",
        completed_at="2026-07-01T10:00:02+00:00",
        processing_time_seconds=2.1,
        model_name="faster-whisper-base",
        model_size="base",
        device_used="cpu",
        compute_type="int8",
        chunk_count=1,
        total_segments=2,
        avg_segment_confidence=0.76,
        stages_completed=["validation", "normalization", "transcription", "postprocessing"],
        retry_count=0,
    )
    metadata = SpeechProcessingMetadata(
        audio_id="test-audio-id-0001",
        framework_version="1.0.0",
        audio_info=audio_info,
        stats=stats,
        project_id="test-project",
    )
    validation = AudioValidationResult(
        is_valid=True,
        errors=[],
        warnings=[],
        audio_info=audio_info,
    )
    return SpeechProcessingResult(
        success=True,
        audio_id="test-audio-id-0001",
        metadata=metadata,
        transcript=sample_transcript,
        validation=validation,
        errors=[],
        warnings=[],
    )
