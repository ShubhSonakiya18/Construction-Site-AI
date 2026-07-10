"""
database/models/audio.py — AudioFile and SpeechTranscript tables.

These tables persist the Sprint 3 pipeline outputs.

AudioFile:
    Stores metadata about each uploaded audio recording.
    Maps to SpeechProcessingResult.metadata.audio_info from Sprint 3.
    The actual audio binary is stored on disk/object storage (future Sprint 7)
    — this table stores the metadata needed to locate and describe the file.

    Why not store the binary in the DB:
    • BLOBs in relational databases cause table bloat and slow backups.
    • Object storage (S3-compatible, or local filesystem for now) is the
      standard approach for file storage in SaaS applications.
    • The file_path column stores where the binary lives; the DB row
      stores queryable metadata (duration, format, validation results).

SpeechTranscript:
    Stores the Sprint 3 transcription result.
    One-to-one with AudioFile (one audio → one transcript).
    The `segments` JSONB column stores the full array of TranscriptSegment
    dicts — Sprint 7 will expose these for timestamp-grounded extraction.

    Why store segments as JSONB (not normalized):
    • A 30-minute recording might have 300+ segments. Each segment has 10+ fields.
    • That's 3,000+ rows in a segments table for one recording. For 10,000
      recordings this becomes 30M rows — expensive to query.
    • Segments are never queried individually (no "show me segment 47").
    • They are fetched as a complete array for extraction grounding.
    • JSONB is the right tool: queryable enough for Sprint 7 grounding,
      compact enough for performance.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from database.models.project import Project
    from database.models.company import User
    from database.models.daily_log import DailyLog


class AudioFile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Metadata for a foreman's voice recording.

    audio_file_id in ConstructionDailyLog maps to AudioFile.id.
    The actual audio binary lives at `file_path` (disk or object storage).
    """

    __tablename__ = "audio_files"

    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        doc="Project this recording belongs to. Nullable — audio may be uploaded "
            "before project assignment in Sprint 7.",
    )
    uploaded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        doc="User who uploaded this recording (usually the foreman).",
    )

    # ── File storage ──────────────────────────────────────────────────────────
    original_filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        doc="The original filename as uploaded by the user.",
    )
    stored_filename: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        doc="The filename as stored on disk/S3. May differ from original (deduplication).",
    )
    file_path: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
        doc="Absolute or relative path to the stored file. Sprint 7 replaces with S3 key.",
    )
    file_size_bytes: Mapped[Optional[int]] = mapped_column(
        Numeric(20, 0),
        nullable=True,
    )
    mime_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="MIME type. e.g. 'audio/wav', 'audio/mpeg'",
    )

    # ── Audio properties ──────────────────────────────────────────────────────
    format: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        doc="File format: wav | mp3 | flac | ogg | m4a | aac | webm",
    )
    duration_seconds: Mapped[Optional[float]] = mapped_column(Numeric(10, 3), nullable=True)
    sample_rate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    channels: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bit_depth: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ── Validation result (Sprint 3 AudioValidator) ───────────────────────────
    is_valid: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        doc="Result of Sprint 3 AudioValidator. NULL means not yet validated.",
    )
    validation_errors: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        doc="List of validation error strings from AudioValidator.",
    )
    validation_warnings: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
    )

    # ── Processing status ─────────────────────────────────────────────────────
    processing_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        doc="Processing lifecycle: pending | transcribing | transcribed | "
            "extracting | extracted | generating | complete | failed",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    project: Mapped[Optional["Project"]] = relationship(
        "Project", back_populates="audio_files"
    )
    transcript: Mapped[Optional["SpeechTranscript"]] = relationship(
        "SpeechTranscript",
        back_populates="audio_file",
        uselist=False,
        cascade="all, delete-orphan",
    )
    daily_log: Mapped[Optional["DailyLog"]] = relationship(
        "DailyLog", back_populates="audio_file", uselist=False
    )

    __table_args__ = (
        Index("ix_audio_files_project_id", "project_id"),
        Index("ix_audio_files_processing_status", "processing_status"),
    )

    def __repr__(self) -> str:
        return f"<AudioFile id={self.id} filename={self.original_filename!r}>"


class SpeechTranscript(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The output of Sprint 3's SpeechProcessingPipeline for one audio file.

    One-to-one with AudioFile. Stores the full transcript text, confidence
    score, language detection, and model metadata needed for audit and
    re-processing.

    `segments` stores the full TranscriptSegment array as JSON for
    timestamp-grounded extraction in Sprint 7.
    """

    __tablename__ = "speech_transcripts"

    audio_file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audio_files.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        doc="One-to-one with AudioFile. CASCADE DELETE: removing the audio file "
            "removes the transcript.",
    )

    # ── Transcript content ────────────────────────────────────────────────────
    raw_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="The full verbatim transcript as produced by Faster Whisper. "
            "Stored for audit and re-extraction without re-transcribing.",
    )
    language_code: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="en",
        doc="ISO 639-1 language code detected by Whisper. e.g. 'en', 'es'",
    )
    language_probability: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4),
        nullable=True,
        doc="Whisper's confidence in the detected language. 0.0–1.0.",
    )
    duration_seconds: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 3), nullable=True
    )
    avg_confidence: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4),
        nullable=True,
        doc="Average segment confidence across the full transcript. 0.0–1.0. "
            "Used by downstream services to flag low-quality transcripts.",
    )

    # ── Model metadata ────────────────────────────────────────────────────────
    model_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    model_size: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, doc="tiny | base | small | medium | large-v3"
    )
    device_used: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, doc="cpu | cuda"
    )
    compute_type: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, doc="int8 | float16 | float32"
    )

    # ── Processing stats ──────────────────────────────────────────────────────
    processing_time_seconds: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 3), nullable=True
    )
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_segments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Full segments (JSONB in production, JSON in SQLite tests) ─────────────
    segments: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        doc="Full array of TranscriptSegment dicts from Sprint 3. "
            "Each segment has: id, text, start, end, avg_logprob, no_speech_prob, "
            "confidence, words[]. Sprint 7 uses these for extraction grounding.",
    )
    stages_completed: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        doc="List of pipeline stage names that completed. "
            "e.g. ['validation', 'normalization', 'transcription', 'postprocessing']",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    audio_file: Mapped["AudioFile"] = relationship(
        "AudioFile", back_populates="transcript"
    )

    __table_args__ = (
        Index("ix_speech_transcripts_audio_file_id", "audio_file_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<SpeechTranscript id={self.id} "
            f"language={self.language_code!r} "
            f"confidence={self.avg_confidence}>"
        )
