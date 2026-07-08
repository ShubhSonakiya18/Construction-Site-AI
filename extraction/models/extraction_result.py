"""
extraction_result.py — Structured result object for every extraction run.

Callers check result.success, never try/except around ExtractionPipeline.extract().
Expected failures (LLM unavailable, bad JSON, schema violation) are results, not exceptions.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractionMetadata:
    model: str
    engine_endpoint: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_seconds: float = 0.0
    attempts: int = 1
    transcript_length: int = 0
    json_repair_applied: bool = False


@dataclass
class ExtractionResult:
    """
    Structured output of ExtractionPipeline.extract().

    extracted_log is a ConstructionDailyLog-shaped dict when success=True.
    validation summarises the Sprint 2 ValidationPipeline result.
    field_confidences maps dot-notation field paths to 0.0–1.0 confidence scores.
    """
    success: bool
    audio_id: str
    extracted_log: Optional[dict]
    validation_passed: bool
    validation_errors: list[str]
    validation_warnings: list[str]
    field_confidences: dict[str, float]
    errors: list[str]
    warnings: list[str]
    metadata: Optional[ExtractionMetadata]

    # ── Convenience accessors ─────────────────────────────────────────────────

    def plain_text(self) -> str:
        """Return extracted full transcript text if available, else empty string."""
        if not self.extracted_log:
            return ""
        completed = self.extracted_log.get("work_completed", [])
        return "; ".join(t.get("task_description", "") for t in completed if t.get("task_description"))

    def current_stage(self) -> Optional[str]:
        if not self.extracted_log:
            return None
        return self.extracted_log.get("current_stage")

    def worker_count(self) -> Optional[int]:
        if not self.extracted_log:
            return None
        workforce = self.extracted_log.get("workforce", {})
        return workforce.get("total_workers_present") if workforce else None

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        meta = None
        if self.metadata:
            meta = {
                "model": self.metadata.model,
                "engine_endpoint": self.metadata.engine_endpoint,
                "prompt_tokens": self.metadata.prompt_tokens,
                "completion_tokens": self.metadata.completion_tokens,
                "duration_seconds": self.metadata.duration_seconds,
                "attempts": self.metadata.attempts,
                "transcript_length": self.metadata.transcript_length,
                "json_repair_applied": self.metadata.json_repair_applied,
            }
        return {
            "success": self.success,
            "audio_id": self.audio_id,
            "extracted_log": self.extracted_log,
            "validation": {
                "passed": self.validation_passed,
                "errors": self.validation_errors,
                "warnings": self.validation_warnings,
            },
            "field_confidences": self.field_confidences,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": meta,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    # ── Factory methods ───────────────────────────────────────────────────────

    @classmethod
    def failure(
        cls,
        errors: list[str],
        audio_id: Optional[str] = None,
        metadata: Optional[ExtractionMetadata] = None,
        warnings: Optional[list[str]] = None,
    ) -> "ExtractionResult":
        return cls(
            success=False,
            audio_id=audio_id or str(uuid.uuid4()),
            extracted_log=None,
            validation_passed=False,
            validation_errors=[],
            validation_warnings=[],
            field_confidences={},
            errors=errors,
            warnings=warnings or [],
            metadata=metadata,
        )
