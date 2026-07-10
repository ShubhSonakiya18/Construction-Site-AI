"""
database/repositories/audio.py — AudioFile and SpeechTranscript repositories.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models.audio import AudioFile, SpeechTranscript
from database.repositories.base import BaseRepository


class AudioRepository(BaseRepository[AudioFile]):
    """Repository for AudioFile (voice recording metadata)."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, AudioFile)

    def list_by_project(
        self,
        project_id: UUID,
        *,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AudioFile]:
        """List audio files for a project, optionally filtered by processing_status."""
        stmt = (
            select(AudioFile)
            .where(AudioFile.project_id == project_id)
        )
        if status is not None:
            stmt = stmt.where(AudioFile.processing_status == status)
        stmt = stmt.order_by(AudioFile.created_at.desc()).limit(limit).offset(offset)
        return list(self._session.execute(stmt).scalars().all())

    def list_pending(self) -> list[AudioFile]:
        """Return all audio files waiting to be transcribed (status='pending')."""
        stmt = (
            select(AudioFile)
            .where(AudioFile.processing_status == "pending")
            .order_by(AudioFile.created_at)
        )
        return list(self._session.execute(stmt).scalars().all())

    def mark_status(self, audio_file: AudioFile, status: str) -> AudioFile:
        """Update processing_status and flush to session.

        Valid statuses: pending | transcribing | transcribed | extracting |
                        extracted | generating | complete | failed
        """
        audio_file.processing_status = status
        self._session.flush()
        return audio_file

    def get_with_transcript(self, audio_file_id: UUID) -> Optional[AudioFile]:
        """Return an AudioFile with its SpeechTranscript eagerly loaded."""
        from sqlalchemy.orm import selectinload
        stmt = (
            select(AudioFile)
            .where(AudioFile.id == audio_file_id)
            .options(selectinload(AudioFile.transcript))
        )
        return self._session.execute(stmt).scalar_one_or_none()


class SpeechTranscriptRepository(BaseRepository[SpeechTranscript]):
    """Repository for SpeechTranscript (Faster Whisper output)."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, SpeechTranscript)

    def get_by_audio_file(self, audio_file_id: UUID) -> Optional[SpeechTranscript]:
        """Return the transcript for a given audio file (one-to-one)."""
        stmt = (
            select(SpeechTranscript)
            .where(SpeechTranscript.audio_file_id == audio_file_id)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def list_low_confidence(self, threshold: float = 0.7) -> list[SpeechTranscript]:
        """Return transcripts with avg_confidence below the threshold.

        Used by Sprint 7 API to flag logs that may need manual review.
        """
        stmt = (
            select(SpeechTranscript)
            .where(SpeechTranscript.avg_confidence < threshold)
            .order_by(SpeechTranscript.avg_confidence)
        )
        return list(self._session.execute(stmt).scalars().all())
