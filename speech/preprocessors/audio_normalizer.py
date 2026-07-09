"""
speech/preprocessors/audio_normalizer.py — Volume normalization before STT.

Whisper performs well on audio in the -20 dBFS to -3 dBFS range. Recordings
from phone microphones are often quieter (-30 to -40 dBFS). Normalization
brings them into the optimal range without clipping.

The normalizer loads audio into a numpy array, normalizes, and writes back to
a temporary WAV file. The pipeline passes this temp file to Faster Whisper.
Temp files are cleaned up by the pipeline, not by this module.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_TARGET_PEAK_DB: float = -3.0   # dBFS target peak after normalization
_TARGET_RMS_DB: float = -20.0   # dBFS target RMS; peak takes priority


class AudioNormalizer:
    """
    Normalizes audio volume to a target peak level.

    Uses peak normalization (scale so the loudest sample hits TARGET_PEAK_DB).
    If soundfile/numpy are unavailable, normalize() is a no-op that returns the
    original path — Whisper can still transcribe unnormalized audio.
    """

    def normalize(self, input_path: str, target_dir: str | None = None) -> str:
        """
        Return path to a normalized WAV file.

        If normalization is skipped (due to missing libraries or flat signal),
        the original path is returned unchanged so the pipeline can continue.
        """
        try:
            return self._normalize(input_path, target_dir)
        except ImportError:
            logger.debug(
                "soundfile/numpy not available; skipping normalization for %s",
                Path(input_path).name,
            )
            return input_path
        except Exception as exc:
            logger.warning(
                "Normalization failed for %s: %s. Proceeding without normalization.",
                Path(input_path).name,
                exc,
            )
            return input_path

    def _normalize(self, input_path: str, target_dir: str | None) -> str:
        import numpy as np
        import soundfile as sf

        audio, sr = sf.read(input_path, always_2d=False)

        # Convert to float32 if needed.
        # soundfile.read() normalizes PCM integer audio to [-1.0, 1.0],
        # so no additional integer-range scaling is required here.
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        peak = np.abs(audio).max()
        if peak < 1e-8:
            # Silent file — skip normalization (validator should catch this)
            logger.debug("Audio is silent, skipping normalization")
            return input_path

        # Peak normalize to target level
        target_linear = 10 ** (_TARGET_PEAK_DB / 20.0)
        gain = target_linear / peak
        normalized = np.clip(audio * gain, -1.0, 1.0)

        # Write to temp file in target_dir (or system temp)
        tmp_dir = target_dir or tempfile.gettempdir()
        tmp_path = os.path.join(
            tmp_dir,
            f"speech_norm_{os.getpid()}_{Path(input_path).stem}.wav",
        )
        sf.write(tmp_path, normalized, sr, subtype="FLOAT")
        logger.debug(
            "Normalized %s: peak gain %.2f dB -> wrote %s",
            Path(input_path).name,
            20 * np.log10(gain),
            Path(tmp_path).name,
        )
        return tmp_path
