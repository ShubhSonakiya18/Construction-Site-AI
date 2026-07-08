"""
speech/models/metadata.py — Audio file info and processing statistics.

These are populated by the metadata extractor (pre-transcription) and the
pipeline itself (post-transcription). Together they form the audit trail
attached to every SpeechProcessingResult.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AudioFileInfo:
    """
    Physical properties of the audio file, extracted before any transcription.

    Populated by speech.metadata.extractor.MetadataExtractor. The validator
    reads these values to decide whether to accept or reject the file.
    """
    file_path: str
    file_name: str
    file_size_bytes: int
    format: str                         # "wav", "mp3", "m4a", "flac", "ogg"
    duration_seconds: float
    sample_rate: int                    # Hz, e.g. 16000, 44100
    channels: int                       # 1=mono, 2=stereo
    bit_depth: int | None = None        # bits per sample (None if lossy)
    codec: str | None = None            # codec string from probe
    is_readable: bool = True            # False if file is corrupt / unreadable

    def file_size_mb(self) -> float:
        return round(self.file_size_bytes / (1024 * 1024), 2)

    def is_mono(self) -> bool:
        return self.channels == 1

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "file_name": self.file_name,
            "file_size_bytes": self.file_size_bytes,
            "file_size_mb": self.file_size_mb(),
            "format": self.format,
            "duration_seconds": round(self.duration_seconds, 3),
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "bit_depth": self.bit_depth,
            "codec": self.codec,
            "is_readable": self.is_readable,
        }


@dataclass
class ProcessingStats:
    """
    Timing and resource statistics for one pipeline run.

    Used by the report layer to surface performance data without needing to
    parse log output.
    """
    started_at: str                         # ISO 8601 UTC string
    completed_at: str = ""                  # filled when pipeline finishes
    processing_time_seconds: float = 0.0
    model_name: str = ""                    # e.g. "faster-whisper-medium"
    model_size: str = ""                    # e.g. "medium"
    device_used: str = ""                   # "cpu" or "cuda"
    compute_type: str = ""                  # "int8", "float16", etc.
    chunk_count: int = 1                    # number of audio chunks processed
    total_segments: int = 0
    avg_segment_confidence: float = 0.0
    stages_completed: list[str] = field(default_factory=list)
    retry_count: int = 0

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "processing_time_seconds": round(self.processing_time_seconds, 3),
            "model_name": self.model_name,
            "model_size": self.model_size,
            "device_used": self.device_used,
            "compute_type": self.compute_type,
            "chunk_count": self.chunk_count,
            "total_segments": self.total_segments,
            "avg_segment_confidence": round(self.avg_segment_confidence, 4),
            "stages_completed": self.stages_completed,
            "retry_count": self.retry_count,
        }


@dataclass
class SpeechProcessingMetadata:
    """
    Complete metadata envelope attached to every SpeechProcessingResult.

    This is what the database (Sprint 6) stores in the audio_files table and
    what the API (Sprint 7) returns alongside the transcript.
    """
    audio_id: str                           # UUID for this processing run
    framework_version: str                  # speech package semver
    audio_info: AudioFileInfo | None = None
    stats: ProcessingStats | None = None
    project_id: str | None = None           # future: link to a project UUID
    pipeline_version: str = "1.0.0"

    def to_dict(self) -> dict:
        return {
            "audio_id": self.audio_id,
            "framework_version": self.framework_version,
            "pipeline_version": self.pipeline_version,
            "project_id": self.project_id,
            "audio_info": self.audio_info.to_dict() if self.audio_info else None,
            "stats": self.stats.to_dict() if self.stats else None,
        }
