"""
speech/metadata/extractor.py — Extracts rich metadata before and after transcription.

The extractor wraps AudioLoader and adds processing-time context. It is the
module that knows both the physical file facts (from AudioLoader) and the
pipeline execution facts (timing, model used).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from speech.loaders.audio_loader import AudioLoader
from speech.models.metadata import AudioFileInfo, ProcessingStats, SpeechProcessingMetadata
from speech.utils.constants import FRAMEWORK_VERSION


class MetadataExtractor:
    """
    Builds SpeechProcessingMetadata for a pipeline run.

    Usage:
        extractor = MetadataExtractor()
        metadata = extractor.create(file_path)
        # ... transcription ...
        extractor.finalize(metadata, stats_updates)
    """

    def __init__(self) -> None:
        self._loader = AudioLoader()

    def create(
        self,
        file_path: str,
        project_id: str | None = None,
        audio_id: str | None = None,
    ) -> SpeechProcessingMetadata:
        """
        Build a SpeechProcessingMetadata object at the start of a pipeline run.

        Populates audio_info immediately. stats is populated by finalize().
        """
        resolved_id = audio_id or str(uuid.uuid4())
        audio_info = self._loader.load(file_path)
        stats = ProcessingStats(
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        return SpeechProcessingMetadata(
            audio_id=resolved_id,
            framework_version=FRAMEWORK_VERSION,
            audio_info=audio_info,
            stats=stats,
            project_id=project_id,
        )

    @staticmethod
    def finalize(
        metadata: SpeechProcessingMetadata,
        model_size: str = "",
        device_used: str = "",
        compute_type: str = "",
        total_segments: int = 0,
        avg_confidence: float = 0.0,
        chunk_count: int = 1,
        stages_completed: list[str] | None = None,
        retry_count: int = 0,
    ) -> None:
        """
        Update processing stats in place after transcription completes.

        Modifies metadata.stats directly (the SpeechProcessingResult already
        holds a reference to this object).
        """
        if metadata.stats is None:
            return

        now = datetime.now(timezone.utc)
        started = datetime.fromisoformat(metadata.stats.started_at)
        elapsed = (now - started).total_seconds()

        metadata.stats.completed_at = now.isoformat()
        metadata.stats.processing_time_seconds = elapsed
        metadata.stats.model_name = f"faster-whisper-{model_size}" if model_size else ""
        metadata.stats.model_size = model_size
        metadata.stats.device_used = device_used
        metadata.stats.compute_type = compute_type
        metadata.stats.total_segments = total_segments
        metadata.stats.avg_segment_confidence = avg_confidence
        metadata.stats.chunk_count = chunk_count
        metadata.stats.stages_completed = stages_completed or []
        metadata.stats.retry_count = retry_count
