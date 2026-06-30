"""
speech/loaders/audio_loader.py — Load audio file metadata without full decoding.

AudioLoader does NOT load the entire audio into memory. It reads only what is
needed to populate AudioFileInfo: duration, sample rate, channel count, bit depth.
This is fast enough to call on every file in a batch without GPU or large memory.

soundfile is used for WAV/FLAC/OGG (native support, no ffmpeg needed).
For MP3/M4A/AAC formats, we fall back to a lightweight header parse or librosa
if available. The pipeline can still transcribe these files even if metadata
extraction partially fails — the STT engine does its own format handling.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from speech.loaders.format_detector import detect_format
from speech.models.metadata import AudioFileInfo

logger = logging.getLogger(__name__)


def _load_with_soundfile(path: str) -> tuple[int, int, int | None, float]:
    """
    Returns (sample_rate, channels, bit_depth, duration_seconds) using soundfile.
    Raises ImportError if soundfile is not installed.
    Raises RuntimeError if the file cannot be read.
    """
    import soundfile as sf  # deferred: not available in all environments

    info = sf.info(path)
    bit_depth: int | None = None
    subtype = info.subtype.upper()
    if "16" in subtype:
        bit_depth = 16
    elif "24" in subtype:
        bit_depth = 24
    elif "32" in subtype:
        bit_depth = 32
    elif "8" in subtype:
        bit_depth = 8

    return info.samplerate, info.channels, bit_depth, info.duration


def _load_with_librosa(path: str) -> tuple[int, int, int | None, float]:
    """
    Fallback metadata reader using librosa (supports MP3/M4A via ffmpeg).
    Returns (sample_rate, channels, bit_depth, duration_seconds).
    Raises ImportError if librosa is not installed.
    """
    import librosa  # deferred

    duration = librosa.get_duration(path=path)
    y, sr = librosa.load(path, sr=None, mono=False, duration=0.1)
    channels = 1 if y.ndim == 1 else y.shape[0]
    return sr, channels, None, duration


class AudioLoader:
    """
    Extracts AudioFileInfo from an audio file path without fully decoding it.

    The loader is stateless — every call to load() is independent.
    """

    def load(self, file_path: str | Path) -> AudioFileInfo:
        """
        Return AudioFileInfo for the given file.

        On unreadable or corrupt files, returns AudioFileInfo with
        is_readable=False and safe default values. The validator will reject
        these files with a clear error message.
        """
        path = Path(file_path)
        fmt = detect_format(path)
        file_size = self._safe_file_size(path)
        base = AudioFileInfo(
            file_path=str(path.resolve()),
            file_name=path.name,
            file_size_bytes=file_size,
            format=fmt,
            duration_seconds=0.0,
            sample_rate=0,
            channels=0,
            is_readable=False,
        )

        if not path.exists():
            logger.debug("File not found: %s", path)
            return base

        # Try soundfile first (fast, no ffmpeg needed)
        try:
            sr, ch, bd, dur = _load_with_soundfile(str(path))
            return AudioFileInfo(
                file_path=str(path.resolve()),
                file_name=path.name,
                file_size_bytes=file_size,
                format=fmt,
                duration_seconds=dur,
                sample_rate=sr,
                channels=ch,
                bit_depth=bd,
                is_readable=True,
            )
        except ImportError:
            logger.debug("soundfile not available; trying librosa")
        except Exception as exc:
            logger.debug("soundfile failed for %s: %s", path.name, exc)

        # Fall back to librosa (handles MP3/M4A if ffmpeg is installed)
        try:
            sr, ch, bd, dur = _load_with_librosa(str(path))
            return AudioFileInfo(
                file_path=str(path.resolve()),
                file_name=path.name,
                file_size_bytes=file_size,
                format=fmt,
                duration_seconds=dur,
                sample_rate=sr,
                channels=ch,
                bit_depth=bd,
                is_readable=True,
            )
        except ImportError:
            logger.debug("librosa not available")
        except Exception as exc:
            logger.debug("librosa failed for %s: %s", path.name, exc)

        # Could not read metadata — mark as unreadable but return best-effort info
        logger.warning(
            "Could not read audio metadata for %s. "
            "Install soundfile (pip install soundfile) to fix this.",
            path.name,
        )
        return base

    @staticmethod
    def _safe_file_size(path: Path) -> int:
        try:
            return os.path.getsize(path)
        except OSError:
            return 0
