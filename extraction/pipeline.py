"""
pipeline.py — ExtractionPipeline: the public entry point for the extraction framework.

Flow for each extract() call:
    1. Build prompt from transcript text
    2. Send to extraction engine (LLM) via BaseLLMProvider interface
    3. Parse JSON from raw LLM response (with repair)
    4. Validate extracted record against schema + business rules
    5. Return ExtractionResult — never raises for expected failures

Usage:
    from extraction import ExtractionPipeline

    pipeline = ExtractionPipeline()
    result = pipeline.extract("Today we poured the foundation slab...")
    if result.success:
        print(result.current_stage())
        print(result.to_json())
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from extraction.config import ExtractionConfig
from extraction.engines.base_engine import BaseLLMProvider
from extraction.engines.factory import EngineFactory
from extraction.models.extraction_result import ExtractionMetadata, ExtractionResult
from extraction.postprocessors.json_repairer import JSONRepairError, repair_json
from extraction.prompts.builder import PromptBuilder
from extraction.validators.schema_validator import SchemaValidator

logger = logging.getLogger(__name__)


def _load_enums(knowledge_dir: str) -> tuple[list[str], list[str], list[str]]:
    """Load stage/weather/trade enums from KnowledgeBase. Returns empty lists on failure."""
    try:
        from dataset_generation_framework.core.knowledge_loader import KnowledgeBase
        kb = KnowledgeBase()
        return kb.stage_enum(), kb.weather_condition_enum(), kb.trade_enum()
    except Exception as exc:
        logger.warning("Could not load enums from KnowledgeBase: %s", exc)
        return [], [], []


class ExtractionPipeline:
    """
    Orchestrates transcript → ConstructionDailyLog extraction.

    Accepts an optional engine= argument for dependency injection (used in tests
    via a mock BaseLLMProvider). Defaults to the provider configured in ExtractionConfig.
    """

    def __init__(
        self,
        config: Optional[ExtractionConfig] = None,
        engine: Optional[BaseLLMProvider] = None,
        validator: Optional[SchemaValidator] = None,
    ) -> None:
        self._config = config or ExtractionConfig()

        stage_enum, weather_enum, trade_enum = _load_enums(self._config.knowledge_dir)

        self._prompt_builder = PromptBuilder(
            stage_enum=stage_enum,
            weather_enum=weather_enum,
            trade_enum=trade_enum,
        )

        if engine is not None:
            self._engine = engine
        else:
            self._engine = EngineFactory.create_from_config(
                self._config,
                system_prompt=self._prompt_builder.system_prompt,
            )

        self._validator = validator or SchemaValidator(self._config.knowledge_dir)

    # ── Public API ────────────────────────────────────────────────────────────

    def extract(
        self,
        transcript_text: str,
        audio_id: Optional[str] = None,
        log_date: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> ExtractionResult:
        """
        Extract a ConstructionDailyLog from transcript text.

        Never raises for expected failure conditions. Returns ExtractionResult
        with success=False and errors populated instead.
        """
        run_id = audio_id or str(uuid.uuid4())
        t_start = time.monotonic()

        if not transcript_text or not transcript_text.strip():
            return ExtractionResult.failure(
                errors=["Transcript is empty — nothing to extract."],
                audio_id=run_id,
            )

        if not self._engine.is_available():
            return ExtractionResult.failure(
                errors=[
                    f"Extraction engine not available (provider={self._config.provider}). "
                    f"Check your API key and connectivity. Endpoint: {self._engine.host}"
                ],
                audio_id=run_id,
            )

        prompt = self._prompt_builder.build_prompt(
            transcript_text=transcript_text,
            log_date=log_date,
            project_id=project_id,
        )

        raw_text = ""
        usage: dict = {}
        attempt = 0
        last_error: Optional[str] = None
        delay = self._config.retry_delay_seconds

        for attempt in range(1, self._config.max_retries + 1):
            try:
                raw_text, usage = self._engine.extract(prompt)
                last_error = None
                break
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "ExtractionPipeline: attempt %d/%d failed: %s",
                    attempt, self._config.max_retries, exc,
                )
                if attempt < self._config.max_retries:
                    time.sleep(delay)
                    delay *= self._config.retry_backoff

        if last_error:
            return ExtractionResult.failure(
                errors=[f"LLM call failed after {self._config.max_retries} attempts: {last_error}"],
                audio_id=run_id,
                metadata=ExtractionMetadata(
                    model=self._engine.model_name,
                    engine_endpoint=self._engine.host,
                    attempts=attempt,
                    transcript_length=len(transcript_text),
                    duration_seconds=time.monotonic() - t_start,
                ),
            )

        # Parse JSON from raw LLM output
        try:
            extracted, was_repaired = repair_json(raw_text)
        except JSONRepairError as exc:
            return ExtractionResult.failure(
                errors=[f"LLM response is not valid JSON: {exc}"],
                audio_id=run_id,
                metadata=ExtractionMetadata(
                    model=self._engine.model_name,
                    engine_endpoint=self._engine.host,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    attempts=attempt,
                    transcript_length=len(transcript_text),
                    duration_seconds=time.monotonic() - t_start,
                ),
            )

        # LLM signalled extraction is not possible
        if extracted.get("extraction_possible") is False:
            return ExtractionResult.failure(
                errors=["LLM determined extraction is not possible from this transcript."],
                audio_id=run_id,
                metadata=ExtractionMetadata(
                    model=self._engine.model_name,
                    engine_endpoint=self._engine.host,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    attempts=attempt,
                    transcript_length=len(transcript_text),
                    duration_seconds=time.monotonic() - t_start,
                ),
            )

        # Ensure required root fields are present
        warnings: list[str] = []
        if was_repaired:
            warnings.append("JSON was extracted from surrounding LLM text (markdown fence or prose).")

        extracted.setdefault("log_id", run_id)
        extracted.setdefault("schema_version", "1.0.0")
        extracted.setdefault("log_source", "voice_recording")
        extracted["audio_file_id"] = run_id

        # Validate
        validation = self._validator.validate(extracted)

        duration = time.monotonic() - t_start
        meta = ExtractionMetadata(
            model=self._engine.model_name,
            engine_endpoint=self._engine.host,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            duration_seconds=duration,
            attempts=attempt,
            transcript_length=len(transcript_text),
            json_repair_applied=was_repaired,
        )

        return ExtractionResult(
            success=True,
            audio_id=run_id,
            extracted_log=extracted,
            validation_passed=validation.passed,
            validation_errors=validation.errors,
            validation_warnings=validation.warnings,
            field_confidences=self._compute_field_confidences(extracted),
            errors=[],
            warnings=warnings + validation.warnings,
            metadata=meta,
        )

    def extract_from_speech_result(self, speech_result: object) -> ExtractionResult:
        """
        Convenience method: extract from a SpeechProcessingResult produced by Sprint 3.

        speech_result must have .success: bool, .plain_text() -> str, .audio_id: str.
        """
        if not getattr(speech_result, "success", False):
            return ExtractionResult.failure(
                errors=["SpeechProcessingResult.success is False — transcript not available."],
                audio_id=getattr(speech_result, "audio_id", None),
            )
        text = speech_result.plain_text() if callable(getattr(speech_result, "plain_text", None)) else ""
        return self.extract(
            transcript_text=text,
            audio_id=getattr(speech_result, "audio_id", None),
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _compute_field_confidences(self, extracted: dict) -> dict[str, float]:
        """
        Assign simple confidence scores based on field presence and type.

        A present non-null value gets 0.9; absent or null gets 0.0.
        Arrays with content get 0.85; empty arrays get 0.1.
        This is a heuristic — a future sprint can add LLM-reported logprobs.
        """
        key_fields = [
            "current_stage",
            "log_date",
            "weather.morning_condition",
            "workforce.total_workers_present",
            "work_completed",
            "materials",
            "safety.safety_meeting_held",
            "delays",
            "tomorrows_plan.planned_tasks",
        ]
        confidences: dict[str, float] = {}
        for field_path in key_fields:
            val = self._get_nested(extracted, field_path)
            if val is None:
                confidences[field_path] = 0.0
            elif isinstance(val, list):
                confidences[field_path] = 0.85 if val else 0.1
            else:
                confidences[field_path] = 0.9
        return confidences

    @staticmethod
    def _get_nested(d: dict, dot_path: str):
        parts = dot_path.split(".")
        val = d
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            else:
                return None
        return val
