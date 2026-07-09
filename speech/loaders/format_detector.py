"""
speech/loaders/format_detector.py — File format detection by extension and magic bytes.

We check both the file extension AND the first 12 bytes of the file (magic
bytes / file signature). A file renamed from .mp3 to .wav is caught here
before wasting time on a transcription attempt.
"""
from __future__ import annotations

import os
from pathlib import Path

from speech.utils.constants import SUPPORTED_AUDIO_FORMATS

# Magic byte signatures: format -> list of (offset, bytes) tuples.
# A file matches if ANY signature matches (some formats have multiple valid headers).
_MAGIC: dict[str, list[tuple[int, bytes]]] = {
    "wav":  [(0, b"RIFF")],
    "mp3":  [(0, b"\xff\xfb"), (0, b"\xff\xf3"), (0, b"\xff\xf2"), (0, b"ID3")],
    "flac": [(0, b"fLaC")],
    "ogg":  [(0, b"OggS")],
    "m4a":  [(4, b"ftyp")],   # MP4/M4A container
    "aac":  [(0, b"\xff\xf1"), (0, b"\xff\xf9")],
    "webm": [(0, b"\x1a\x45\xdf\xa3")],
}


def detect_format(file_path: str | Path) -> str:
    """
    Return the audio format string (e.g. "wav") for the given file.

    Strategy:
    1. Check file extension (fast path).
    2. If extension is unknown or ambiguous, read first 12 bytes and match
       against known magic bytes.
    3. Return empty string if format cannot be determined.
    """
    path = Path(file_path)
    ext = path.suffix.lstrip(".").lower()

    if ext in SUPPORTED_AUDIO_FORMATS:
        return ext

    # Fall back to magic byte detection for files with wrong/missing extensions
    try:
        with open(path, "rb") as f:
            header = f.read(12)
    except OSError:
        return ""

    for fmt, signatures in _MAGIC.items():
        for offset, magic in signatures:
            if header[offset: offset + len(magic)] == magic:
                return fmt

    return ""


def is_supported_format(file_path: str | Path) -> bool:
    """Return True if the file appears to be a supported audio format."""
    return detect_format(file_path) in SUPPORTED_AUDIO_FORMATS
