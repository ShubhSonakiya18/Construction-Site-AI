"""
speech/preprocessors/noise_reducer.py — Optional noise reduction using noisereduce.

Construction sites have significant background noise: generators, compressors,
power tools, traffic. This module reduces stationary noise (constant hum) before
transcription. Non-stationary noise (sudden bangs) is handled by Whisper's
VAD filter instead.

noisereduce is an optional dependency. If not installed, reduce() is a no-op
and returns the original path. Whisper handles moderate noise natively.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def _is_noisereduce_available() -> bool:
    try:
        import noisereduce  # noqa: F401
        return True
    except ImportError:
        return False


class NoiseReducer:
    """
    Applies stationary noise reduction to audio before STT.

    If noisereduce is not installed, reduce() is a transparent pass-through.
    Install with: pip install noisereduce
    """

    def __init__(self, strength: float = 0.75) -> None:
        """
        strength: 0.0 (no reduction) to 1.0 (aggressive). 0.75 is a safe default
        that removes most HVAC/generator hum without affecting speech clarity.
        """
        self._strength = max(0.0, min(1.0, strength))
        self._available = _is_noisereduce_available()
        if not self._available:
            logger.debug(
                "noisereduce not installed. Noise reduction disabled. "
                "Install with: pip install noisereduce"
            )

    @property
    def is_available(self) -> bool:
        return self._available

    def reduce(self, input_path: str, target_dir: str | None = None) -> str:
        """
        Return path to a noise-reduced WAV file.

        Returns input_path unchanged if noisereduce is unavailable or fails.
        """
        if not self._available:
            return input_path

        try:
            return self._reduce(input_path, target_dir)
        except Exception as exc:
            logger.warning(
                "Noise reduction failed for %s: %s. Proceeding without it.",
                Path(input_path).name,
                exc,
            )
            return input_path

    def _reduce(self, input_path: str, target_dir: str | None) -> str:
        import noisereduce as nr
        import numpy as np
        import soundfile as sf

        audio, sr = sf.read(input_path, always_2d=False)
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # For stereo, process each channel independently
        if audio.ndim == 2:
            reduced_channels = []
            for ch in range(audio.shape[1]):
                reduced_channels.append(
                    nr.reduce_noise(y=audio[:, ch], sr=sr, prop_decrease=self._strength)
                )
            reduced = np.stack(reduced_channels, axis=1)
        else:
            reduced = nr.reduce_noise(y=audio, sr=sr, prop_decrease=self._strength)

        tmp_dir = target_dir or tempfile.gettempdir()
        tmp_path = os.path.join(
            tmp_dir,
            f"speech_denoised_{os.getpid()}_{Path(input_path).stem}.wav",
        )
        sf.write(tmp_path, reduced, sr, subtype="FLOAT")
        logger.debug(
            "Noise reduction applied to %s -> %s",
            Path(input_path).name,
            Path(tmp_path).name,
        )
        return tmp_path
