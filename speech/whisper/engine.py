"""
speech/whisper/engine.py — STT engine abstraction + Faster Whisper implementation.

Architecture rule: NOTHING outside this file imports faster_whisper.
Every other module in the application works with Transcript / TranscriptSegment
dataclasses. Replacing Faster Whisper with another engine means implementing
BaseSTTEngine and passing the new engine to SpeechProcessingConfig — zero
business logic changes.

FasterWhisperEngine uses lazy model loading: the ~150 MB–3 GB model is not
downloaded or loaded until the first transcribe() call. This allows importing
the speech package without triggering a model download.
"""
from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from pathlib import Path

from speech.config import WhisperConfig
from speech.models.transcript import Transcript, TranscriptSegment, WordTimestamp
from speech.utils.retry import retry

logger = logging.getLogger(__name__)


class BaseSTTEngine(ABC):
    """
    Abstract base for any speech-to-text engine.

    To add a new engine (e.g. OpenAI Whisper API, AssemblyAI, Deepgram):
    1. Subclass BaseSTTEngine.
    2. Implement transcribe() and is_available().
    3. Pass an instance to SpeechProcessingPipeline(engine=YourEngine()).

    No other code needs to change.
    """

    @abstractmethod
    def transcribe(self, audio_path: str) -> Transcript:
        """
        Transcribe the audio file at audio_path and return a Transcript.

        Implementations must:
        - Return a Transcript even for very low-confidence output (the
          postprocessor and caller decide what to do with it).
        - Raise RuntimeError for unrecoverable engine failures (model not
          loaded, OOM, corrupt model files).
        - NOT raise exceptions for empty/silent audio — return a Transcript
          with an empty text string instead.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """
        Return True if the engine's dependencies are installed and the model
        can be loaded. Used by the CLI to give helpful error messages.
        """

    @property
    def engine_name(self) -> str:
        return self.__class__.__name__


class FasterWhisperEngine(BaseSTTEngine):
    """
    Faster Whisper STT engine implementation.

    Faster Whisper (https://github.com/guillaumekln/faster-whisper) is a
    reimplementation of OpenAI's Whisper using CTranslate2 for 4x faster
    inference with the same or better accuracy. Runs fully locally.

    Model is lazy-loaded on first transcribe() call. Subsequent calls reuse
    the loaded model (it stays in memory for the process lifetime).
    """

    def __init__(self, config: WhisperConfig) -> None:
        self._config = config
        self._model = None   # loaded lazily

    def is_available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            return False

    @retry(max_attempts=3, delay_seconds=1.0, backoff=2.0)
    def _load_model(self) -> None:
        """Load the Whisper model into memory. Retried up to 3 times."""
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is not installed. "
                "Run: pip install faster-whisper"
            ) from exc

        cfg = self._config
        logger.info(
            "Loading Faster Whisper model '%s' on device '%s' (%s)...",
            cfg.model_size,
            cfg.device,
            cfg.compute_type,
        )

        import os
        os.makedirs(cfg.model_cache_dir, exist_ok=True)

        self._model = WhisperModel(
            cfg.model_size,
            device=cfg.device,
            compute_type=cfg.compute_type,
            download_root=cfg.model_cache_dir,
        )
        logger.info("Faster Whisper model '%s' loaded successfully.", cfg.model_size)

    def transcribe(self, audio_path: str) -> Transcript:
        """
        Transcribe audio_path and return a Transcript dataclass.

        The first call triggers model loading (may take 5–30 seconds depending
        on model size and hardware). Subsequent calls are fast.
        """
        if self._model is None:
            self._load_model()

        path = Path(audio_path)
        logger.debug("Transcribing '%s' with Faster Whisper '%s'...", path.name, self._config.model_size)

        cfg = self._config

        # The faster_whisper API returns a generator — we consume it fully
        # before building the Transcript so that all segments are available
        # for the avg_confidence calculation.
        raw_segments, info = self._model.transcribe(  # type: ignore[union-attr]
            audio_path,
            language=cfg.language,
            task=cfg.task,
            beam_size=cfg.beam_size,
            vad_filter=cfg.vad_filter,
            word_timestamps=cfg.word_timestamps,
            condition_on_previous_text=cfg.condition_on_previous_text,
        )

        segments: list[TranscriptSegment] = []
        full_text_parts: list[str] = []

        for idx, seg in enumerate(raw_segments):
            words: list[WordTimestamp] = []
            if cfg.word_timestamps and hasattr(seg, "words") and seg.words:
                for w in seg.words:
                    words.append(
                        WordTimestamp(
                            word=w.word,
                            start=w.start,
                            end=w.end,
                            probability=w.probability,
                        )
                    )

            # avg_logprob can be -inf for silent segments; clamp for display
            avg_logprob = seg.avg_logprob if seg.avg_logprob > -1e6 else -10.0
            confidence = float(min(1.0, max(0.0, math.exp(avg_logprob))))

            ts = TranscriptSegment(
                id=idx,
                text=seg.text,
                start=seg.start,
                end=seg.end,
                avg_logprob=avg_logprob,
                no_speech_prob=seg.no_speech_prob,
                confidence=confidence,
                words=words,
            )
            segments.append(ts)
            full_text_parts.append(seg.text.strip())

        full_text = " ".join(p for p in full_text_parts if p)
        duration = info.duration if hasattr(info, "duration") else 0.0

        transcript = Transcript(
            text=full_text,
            language=info.language if hasattr(info, "language") else "",
            language_probability=info.language_probability if hasattr(info, "language_probability") else 0.0,
            duration_seconds=duration,
            segments=segments,
        )

        logger.debug(
            "Transcribed '%s': %d segments, %.1fs, lang=%s (%.0f%%), "
            "avg_conf=%.2f",
            path.name,
            len(segments),
            duration,
            transcript.language,
            transcript.language_probability * 100,
            transcript.avg_confidence(),
        )

        return transcript

    def unload(self) -> None:
        """
        Release the model from memory.

        Call this when batch processing is complete and the model is no longer
        needed, to free GPU/CPU memory for other workloads.
        """
        self._model = None
        logger.debug("Faster Whisper model unloaded.")
