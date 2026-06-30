"""
speech/pipeline.py — The main orchestrator for the Speech Processing Framework.

PUBLIC API
----------
    from speech import SpeechProcessingPipeline, SpeechProcessingConfig

    pipeline = SpeechProcessingPipeline()
    result   = pipeline.process("recording.wav")
    print(result.plain_text())

ARCHITECTURE
------------
The pipeline owns the sequence of operations and error handling. No business
logic module ever calls an STT engine directly. The sequence is:

    1. MetadataExtractor.create()     -- open audio_info + start timer
    2. AudioValidator.validate()      -- 8 blocking checks, 3 warnings
    3. AudioNormalizer.normalize()    -- volume normalization (optional)
    4. NoiseReducer.reduce()          -- noise reduction (optional)
    5. FasterWhisperEngine.transcribe() -- STT via BaseSTTEngine interface
    6. TranscriptCleaner.clean()      -- filler removal + term normalization
    7. MetadataExtractor.finalize()   -- stop timer, attach stats
    8. Return SpeechProcessingResult

Every step is individually recoverable:
- Validation failure   -> SpeechProcessingResult.failure() returned immediately
- Preprocessing error  -> logged as warning; original file used instead
- STT failure          -> SpeechProcessingResult.failure() with full error chain
- Postprocessing error -> logged as warning; raw transcript used instead

BATCH PROCESSING
----------------
    results = pipeline.process_batch(["a.wav", "b.wav", "c.wav"])

REPLACING THE STT ENGINE
-------------------------
    from speech.whisper.engine import BaseSTTEngine

    class MyCustomEngine(BaseSTTEngine):
        def transcribe(self, audio_path: str) -> Transcript: ...
        def is_available(self) -> bool: ...

    pipeline = SpeechProcessingPipeline(engine=MyCustomEngine())

The rest of the application does not change. Only this file and engine.py are
aware that Faster Whisper exists.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Callable

from speech.config import SpeechProcessingConfig
from speech.metadata.extractor import MetadataExtractor
from speech.models.processing_result import AudioValidationResult, SpeechProcessingResult
from speech.models.transcript import Transcript
from speech.postprocessors.transcript_cleaner import TranscriptCleaner
from speech.preprocessors.audio_normalizer import AudioNormalizer
from speech.preprocessors.chunker import AudioChunker
from speech.preprocessors.noise_reducer import NoiseReducer
from speech.validators.audio_validator import AudioValidator
from speech.whisper.engine import BaseSTTEngine, FasterWhisperEngine

logger = logging.getLogger(__name__)


class SpeechProcessingPipeline:
    """
    Engine-agnostic speech processing pipeline.

    Parameters
    ----------
    config : SpeechProcessingConfig | None
        Pipeline configuration. Defaults to SpeechProcessingConfig() which
        reads sensible defaults (base model, CPU, int8, VAD on).
    engine : BaseSTTEngine | None
        STT engine to use. Defaults to FasterWhisperEngine(config.whisper).
        Inject a custom engine for testing or to swap Faster Whisper out.
    """

    def __init__(
        self,
        config: SpeechProcessingConfig | None = None,
        engine: BaseSTTEngine | None = None,
    ) -> None:
        self._config = config or SpeechProcessingConfig()
        self._engine = engine or FasterWhisperEngine(self._config.whisper)

        self._validator = AudioValidator(self._config.validation)
        self._normalizer = AudioNormalizer()
        self._noise_reducer = NoiseReducer(
            strength=self._config.preprocessing.noise_reduction_strength
        )
        self._cleaner = TranscriptCleaner(
            remove_filler_words=self._config.postprocessing.clean_filler_words,
            normalize_construction_terms=self._config.postprocessing.normalize_construction_terms,
        )
        self._chunker = AudioChunker(
            chunk_length_seconds=self._config.preprocessing.chunk_length_seconds,
            overlap_seconds=self._config.preprocessing.chunk_overlap_seconds,
        )
        self._extractor = MetadataExtractor()

    # ── Public API ─────────────────────────────────────────────────────────────

    def process(
        self,
        audio_path: str,
        project_id: str | None = None,
        audio_id: str | None = None,
        export_to: str | None = None,
    ) -> SpeechProcessingResult:
        """
        Process a single audio file through the full pipeline.

        Parameters
        ----------
        audio_path : str
            Path to the audio file to transcribe.
        project_id : str | None
            Optional project identifier embedded in metadata (for Sprint 4+).
        audio_id : str | None
            Optional UUID override. Auto-generated if not provided.
        export_to : str | None
            If set, export the result as JSON to this directory immediately.

        Returns
        -------
        SpeechProcessingResult
            Always returned, even on failure. Check result.success first.
        """
        self._emit_progress("initializing", 0.0)

        # ── Stage 1: Metadata initialisation ──────────────────────────────────
        metadata = self._extractor.create(
            file_path=str(audio_path),
            project_id=project_id,
            audio_id=audio_id,
        )
        stages: list[str] = []
        warnings: list[str] = []

        # ── Stage 2: Validation ───────────────────────────────────────────────
        self._emit_progress("validating", 10.0)
        validation = self._validator.validate(str(audio_path))
        if not validation.is_valid:
            logger.warning("Audio validation failed for %s: %s", audio_path, validation.errors)
            MetadataExtractor.finalize(
                metadata,
                stages_completed=["validation_failed"],
            )
            return SpeechProcessingResult.failure(
                audio_id=metadata.audio_id,
                metadata=metadata,
                errors=validation.errors,
                validation=validation,
            )

        stages.append("validation")
        warnings.extend(validation.warnings)
        self._emit_progress("validated", 20.0)

        # ── Stage 3: Preprocessing ────────────────────────────────────────────
        working_path = str(audio_path)
        temp_dir: str | None = None

        try:
            temp_dir = tempfile.mkdtemp(prefix="speech_pipeline_")

            if self._config.preprocessing.enable_normalization:
                self._emit_progress("normalizing", 30.0)
                try:
                    normalized = self._normalizer.normalize(working_path, temp_dir)
                    working_path = normalized
                    stages.append("normalization")
                except Exception as exc:
                    logger.warning("Audio normalization skipped: %s", exc)
                    warnings.append(f"Normalization skipped: {exc}")

            if self._config.preprocessing.enable_noise_reduction:
                self._emit_progress("reducing_noise", 40.0)
                try:
                    if self._noise_reducer.is_available:
                        reduced = self._noise_reducer.reduce(working_path, temp_dir)
                        working_path = reduced
                        stages.append("noise_reduction")
                    else:
                        warnings.append(
                            "Noise reduction requested but noisereduce is not installed"
                        )
                except Exception as exc:
                    logger.warning("Noise reduction skipped: %s", exc)
                    warnings.append(f"Noise reduction skipped: {exc}")

            # ── Stage 4: STT transcription ─────────────────────────────────────
            self._emit_progress("transcribing", 50.0)
            try:
                raw_transcript = self._engine.transcribe(working_path)
                stages.append("transcription")
            except Exception as exc:
                logger.error("Transcription failed: %s", exc, exc_info=True)
                MetadataExtractor.finalize(
                    metadata,
                    model_size=self._config.whisper.model_size,
                    device_used=self._config.whisper.device,
                    compute_type=self._config.whisper.compute_type,
                    stages_completed=stages + ["transcription_failed"],
                )
                return SpeechProcessingResult.failure(
                    audio_id=metadata.audio_id,
                    metadata=metadata,
                    errors=[f"Transcription error: {exc}"],
                    validation=validation,
                )

            # ── Stage 5: Postprocessing ────────────────────────────────────────
            self._emit_progress("postprocessing", 80.0)
            try:
                transcript = self._cleaner.clean(raw_transcript)
                stages.append("postprocessing")
            except Exception as exc:
                logger.warning("Postprocessing failed, using raw transcript: %s", exc)
                warnings.append(f"Postprocessing skipped: {exc}")
                transcript = raw_transcript

            # Confidence warnings
            avg_conf = transcript.avg_confidence()
            threshold = self._config.postprocessing.low_confidence_warning_threshold
            if avg_conf < threshold and not transcript.is_empty():
                warnings.append(
                    f"Low transcript confidence: {avg_conf:.2%} (threshold {threshold:.2%})"
                )

            # ── Stage 6: Finalize metadata ─────────────────────────────────────
            duration = raw_transcript.duration_seconds
            chunk_count = self._chunker.chunk_count(duration) if duration > 0 else 1

            MetadataExtractor.finalize(
                metadata,
                model_size=self._config.whisper.model_size,
                device_used=self._config.whisper.device,
                compute_type=self._config.whisper.compute_type,
                total_segments=len(transcript.segments),
                avg_confidence=avg_conf,
                chunk_count=chunk_count,
                stages_completed=stages,
                retry_count=0,
            )

            self._emit_progress("complete", 100.0)

            result = SpeechProcessingResult(
                success=True,
                audio_id=metadata.audio_id,
                metadata=metadata,
                transcript=transcript,
                validation=validation,
                errors=[],
                warnings=warnings,
            )

            if export_to:
                self._auto_export(result, export_to)

            return result

        finally:
            if temp_dir:
                self._cleanup_temp(temp_dir)

    def process_batch(
        self,
        audio_paths: list[str],
        project_id: str | None = None,
        export_to: str | None = None,
        on_result: Callable[[SpeechProcessingResult], None] | None = None,
    ) -> list[SpeechProcessingResult]:
        """
        Process a list of audio files sequentially.

        Parameters
        ----------
        audio_paths : list[str]
            Ordered list of audio file paths.
        project_id : str | None
            Project identifier applied to all results.
        export_to : str | None
            If set, each result is exported as JSON to this directory.
        on_result : Callable[[SpeechProcessingResult], None] | None
            Optional callback called after each file completes. Use for
            real-time progress reporting in CLI or API contexts.

        Returns
        -------
        list[SpeechProcessingResult]
            One result per input path, in the same order.
        """
        results: list[SpeechProcessingResult] = []
        total = len(audio_paths)

        for i, path in enumerate(audio_paths):
            logger.info("Batch [%d/%d] processing: %s", i + 1, total, path)
            result = self.process(
                audio_path=path,
                project_id=project_id,
                export_to=export_to,
            )
            results.append(result)
            if on_result:
                try:
                    on_result(result)
                except Exception as exc:
                    logger.warning("on_result callback raised: %s", exc)

        return results

    def unload_engine(self) -> None:
        """Release the STT model from memory. Useful after large batch jobs."""
        if hasattr(self._engine, "unload"):
            self._engine.unload()

    # ── Private helpers ────────────────────────────────────────────────────────

    def _emit_progress(self, stage: str, pct: float) -> None:
        cb = self._config.progress_callback
        if cb is not None:
            try:
                cb(stage, pct)
            except Exception:
                pass

    def _auto_export(self, result: SpeechProcessingResult, export_dir: str) -> None:
        from speech.exporters.json_exporter import JSONExporter
        exporter = JSONExporter()
        out = Path(export_dir) / f"{result.audio_id}.json"
        try:
            exporter.export(result, str(out))
            logger.info("Result exported to: %s", out)
        except Exception as exc:
            logger.warning("Auto-export failed: %s", exc)

    @staticmethod
    def _cleanup_temp(temp_dir: str) -> None:
        """Remove temporary preprocessing files."""
        import shutil
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
