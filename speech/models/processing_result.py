"""
speech/models/processing_result.py — The top-level output of the pipeline.

SpeechProcessingResult is what the rest of the application receives.
It is intentionally self-contained: no caller needs to read intermediate
objects to get the transcript text, confidence, or error information.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from speech.models.metadata import AudioFileInfo, SpeechProcessingMetadata
from speech.models.transcript import Transcript


@dataclass
class AudioValidationResult:
    """
    Output of AudioValidator.validate() — the gate before transcription starts.

    is_valid=False means the pipeline will NOT attempt transcription.
    Errors are blocking; warnings are advisory.
    """
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    audio_info: AudioFileInfo | None = None

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "audio_info": self.audio_info.to_dict() if self.audio_info else None,
        }


@dataclass
class SpeechProcessingResult:
    """
    Complete output of one SpeechProcessingPipeline.process() call.

    The Sprint 4 AI extraction engine reads `transcript.text` (and optionally
    `transcript.segments` for grounding). No other attribute is required for
    normal extraction. The remaining attributes feed the audit trail, UI, and
    database record in later sprints.

    success=False means transcription failed entirely. The errors list explains why.
    Partial success (transcription started but confidence is low) appears as
    success=True with warnings populated.
    """
    success: bool
    audio_id: str
    metadata: SpeechProcessingMetadata
    transcript: Transcript | None = None
    validation: AudioValidationResult | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # ── Convenience accessors ──────────────────────────────────────────────────

    def plain_text(self) -> str:
        """Returns just the transcript string, or empty string on failure."""
        if self.transcript and not self.transcript.is_empty():
            return self.transcript.text
        return ""

    def confidence(self) -> float:
        """Average confidence across all segments. 0.0 if not transcribed."""
        if self.transcript:
            return self.transcript.avg_confidence()
        return 0.0

    def duration_seconds(self) -> float:
        """Audio duration in seconds. 0.0 if metadata unavailable."""
        if self.metadata and self.metadata.audio_info:
            return self.metadata.audio_info.duration_seconds
        if self.transcript:
            return self.transcript.duration_seconds
        return 0.0

    def language(self) -> str:
        """Detected language code, e.g. 'en'. Empty string if not detected."""
        if self.transcript:
            return self.transcript.language
        return ""

    # ── Serialization ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "audio_id": self.audio_id,
            "transcript": self.transcript.to_dict() if self.transcript else None,
            "validation": self.validation.to_dict() if self.validation else None,
            "metadata": self.metadata.to_dict(),
            "errors": self.errors,
            "warnings": self.warnings,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def failure(
        cls,
        audio_id: str,
        metadata: SpeechProcessingMetadata,
        errors: list[str],
        validation: AudioValidationResult | None = None,
    ) -> "SpeechProcessingResult":
        """Factory for a clean failure result — avoids None-guarding in callers."""
        return cls(
            success=False,
            audio_id=audio_id,
            metadata=metadata,
            errors=errors,
            validation=validation,
        )
