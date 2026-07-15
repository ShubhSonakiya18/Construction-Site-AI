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
from database.repositories.tenant import TenantContext, TenantScopedRepository


class AudioRepository(TenantScopedRepository[AudioFile]):
    """Repository for AudioFile (voice recording metadata).

    Tenant scoping (Sprint 8, Subsystem 3): AudioFile.project_id is
    nullable (audio may be uploaded before project assignment — see
    app/api/v1/audio.py's Sprint 7/8 project_id validation history). An
    AudioFile with project_id=None has no company to scope against; see
    get_by_id_scoped()'s docstring for how that case is handled.
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session, AudioFile)

    def get_by_id_scoped(
        self, audio_file_id: UUID, *, tenant: TenantContext
    ) -> Optional[AudioFile]:
        """Tenant-safe replacement for get_by_id() for the status-polling
        endpoint. An AudioFile with project_id=None (uploaded before
        project assignment) is visible ONLY to the user who uploaded it
        (uploaded_by_id match) — there is no company to scope against yet,
        so falling back to "nobody but the uploader can see it" is the
        safe default rather than either "everyone in every company can
        see it" or "nobody can ever see it again." Once project_id is
        assigned, normal company scoping takes over."""
        from database.models.project import Project

        audio_file = self.get_by_id(audio_file_id)
        if audio_file is None:
            return None
        if audio_file.project_id is None:
            return audio_file if audio_file.uploaded_by_id == tenant.user_id else None
        stmt = (
            select(Project)
            .where(Project.id == audio_file.project_id)
            .where(Project.company_id == tenant.company_id)
        )
        project = self._session.execute(stmt).scalar_one_or_none()
        return audio_file if project is not None else None

    def get_by_id_cross_tenant(
        self, audio_file_id: UUID, *, tenant: TenantContext, request_id: Optional[str] = None
    ) -> Optional[AudioFile]:
        """System Admin bypass — see database/repositories/tenant.py
        module docstring."""
        from database.models.project import Project

        audio_file = self.get_by_id(audio_file_id)
        target_company_id = None
        if audio_file is not None and audio_file.project_id is not None:
            stmt = select(Project.company_id).where(Project.id == audio_file.project_id)
            target_company_id = self._session.execute(stmt).scalar_one_or_none()

        self._audit_cross_tenant_access(
            tenant_context_actor=tenant,
            target_company_id=target_company_id,
            entity_type="audio_file",
            entity_id=audio_file_id,
            action="get_by_id_cross_tenant",
            request_id=request_id,
        )
        return audio_file

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
