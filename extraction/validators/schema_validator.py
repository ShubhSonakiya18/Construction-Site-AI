"""
schema_validator.py — Validates extracted ConstructionDailyLog records.

Two-stage validation:
    1. JSON Schema (jsonschema) — structural correctness, enum values, required fields.
    2. Sprint 2 ValidationPipeline — business rules (sequencing, cross-field logic).

Reuses dataset_generation_framework.validation.pipeline unchanged.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

try:
    import jsonschema as _jsonschema
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False


@dataclass
class ValidationSummary:
    passed: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info_notes: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.passed = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def add_info(self, msg: str) -> None:
        self.info_notes.append(msg)


class SchemaValidator:
    """
    Validates an extracted ConstructionDailyLog dict against the Sprint 1 schema
    and Sprint 2 business rules.

    Constructed once per pipeline instance (loads KnowledgeBase once).
    """

    def __init__(self, knowledge_dir: str = "knowledge") -> None:
        self._schema: dict | None = None
        self._pipeline = None
        self._load_ok = False
        self._knowledge_dir = knowledge_dir
        self._init_validators()

    def _init_validators(self) -> None:
        try:
            from dataset_generation_framework.core.knowledge_loader import KnowledgeBase
            from dataset_generation_framework.validation.pipeline import ValidationPipeline

            kb = KnowledgeBase()
            self._schema = kb.raw_schema
            self._pipeline = ValidationPipeline(kb)
            self._load_ok = True
        except Exception as exc:
            logger.warning(
                "SchemaValidator: could not load KnowledgeBase (%s). "
                "Validation will be skipped.",
                exc,
            )

    def validate(self, record: dict) -> ValidationSummary:
        summary = ValidationSummary()

        if not self._load_ok:
            summary.add_warning("Validation skipped: knowledge base not available.")
            return summary

        # Stage 1 — JSON Schema structural check
        if _HAS_JSONSCHEMA and self._schema:
            try:
                _jsonschema.validate(instance=record, schema=self._schema)
            except _jsonschema.ValidationError as exc:
                summary.add_error(f"Schema violation: {exc.message}")
                return summary  # no point running business rules on invalid structure
            except _jsonschema.SchemaError as exc:
                logger.warning("Schema itself is invalid: %s", exc)
        elif not _HAS_JSONSCHEMA:
            summary.add_warning("jsonschema not installed; structural check skipped.")

        # Stage 2 — Business rules (Sprint 2 ValidationPipeline, ai_extraction context)
        if self._pipeline:
            try:
                result = self._pipeline.validate(record, applies_to="ai_extraction")
                for err in result.blocking_errors:
                    summary.add_error(err)
                    summary.passed = False
                for err in result.non_blocking_errors:
                    summary.add_error(err)
                for w in result.warnings:
                    summary.add_warning(w)
                for i in result.info_notes:
                    summary.add_info(i)
            except Exception as exc:
                logger.warning("Business rule validation raised: %s", exc)
                summary.add_warning(f"Business rule check skipped: {exc}")

        return summary
