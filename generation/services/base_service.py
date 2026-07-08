"""
base_service.py — BaseAIService: template method for all AI generation services.

Why the template method pattern:
    All 4 services follow the same flow:
        load prompt → build user message → call LLM → validate content → wrap result

    Duplicating this flow in 4 classes would make each one a maintenance burden —
    changing retry logic or logging would require 4 edits. BaseAIService owns the
    flow; subclasses implement only what differs (service_type, prompt_name,
    _build_user_message). This is the Template Method pattern (Gang of Four, p.325).

Why ONE engine for all services:
    GroqEngine's system_prompt is set at construction time. Modifying Sprint 4's
    GroqEngine to accept per-call system prompts would break the FROZEN interface.
    Solution: system instructions are embedded in the user message (via the prompt
    template file). One shared engine means one is_available() check, one client
    instance, and clean separation of concerns.

Retry strategy:
    Inline exponential backoff (not the @retry decorator from speech/utils/retry.py).
    Why: @retry uses a class-level approach that doesn't expose retry_count to the
    returned ServiceOutput metadata. The inline loop gives us that count for observability.
    The retry logic here is ~30 lines — well within "don't abstract until 3 copies."

Sprint 5.1 — Prompt caching:
    The instance-level self._loaded_prompt cache that existed in Sprint 5.0 has been
    removed. BaseAIService now always calls self._prompt_loader.load(self.prompt_name).

    Why: PromptLoader now has mtime-aware cache invalidation. If a prompt file is
    edited, PromptLoader detects the changed mtime and evicts the stale entry. But
    if BaseAIService caches the LoadedPrompt itself, that stale-detection never
    triggers — the mtime check is bypassed entirely.

    Performance: identical. PromptLoader.load() returns the cached object after
    the mtime check (O(1) dict lookup + one os.stat). No redundant disk reads.

Sprint 5.1 — Observability:
    Each generate() call now emits typed events to the METRICS accumulator and
    fires GenerationStarted / GenerationCompleted / GenerationFailed events.
    The generation_id from ServiceMetadata is the correlation key across all events.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from uuid import uuid4

from extraction.engines.base_engine import BaseLLMProvider
from generation.config import GenerationConfig
from generation.models.outputs import ServiceMetadata, ServiceOutput, ServiceType
from generation.observability.events import (
    GenerationCompletedEvent,
    GenerationFailedEvent,
    GenerationStartedEvent,
    RetryStartedEvent,
    ValidationFailedEvent,
)
from generation.observability.metrics import METRICS
from generation.prompts.loader import LoadedPrompt, PromptLoader
from generation.validators.content_validator import ContentValidator

logger = logging.getLogger(__name__)


class BaseAIService(ABC):
    """Abstract base for all AI generation services.

    Subclasses must implement:
        service_type (property)  — identifies this service
        prompt_name  (property)  — file stem under generation/prompts/
        _build_user_message()    — formats log dict into the LLM user message
    """

    def __init__(
        self,
        engine: BaseLLMProvider,
        prompt_loader: PromptLoader,
        validator: ContentValidator,
        config: GenerationConfig,
    ) -> None:
        self._engine = engine
        self._prompt_loader = prompt_loader
        self._validator = validator
        self._config = config

    @property
    @abstractmethod
    def service_type(self) -> ServiceType: ...

    @property
    @abstractmethod
    def prompt_name(self) -> str: ...

    @abstractmethod
    def _build_user_message(self, log: dict) -> str:
        """Format the relevant sections of the log into the LLM user message."""

    # ── Template method ───────────────────────────────────────────────────────

    def generate(self, log: dict) -> ServiceOutput:
        """Run the full generation pipeline for this service."""
        generation_id = str(uuid4())
        log_id = log.get("log_id", "")

        # Load prompt via PromptLoader (mtime-aware cache handles invalidation)
        loaded = self._prompt_loader.load(self.prompt_name)
        user_message = self._build_user_message(log)
        full_prompt = f"{loaded.template}\n\n---\n\n{user_message}"

        METRICS.record_started(GenerationStartedEvent(
            service_type=self.service_type.value,
            generation_id=generation_id,
            log_id=log_id,
            model=self._engine.model_name,
            prompt_name=loaded.metadata.name,
            prompt_version=loaded.metadata.version,
        ))

        retry_count = 0
        delay = self._config.retry_delay_seconds
        last_error = ""

        for attempt in range(self._config.max_retries + 1):
            t_start = time.monotonic()
            try:
                logger.info(
                    "generation.%s: attempt %d/%d model=%s",
                    self.service_type.value,
                    attempt + 1,
                    self._config.max_retries + 1,
                    self._engine.model_name,
                )
                raw_text, usage = self._engine.extract(full_prompt)
                response_time = time.monotonic() - t_start

                t_val = time.monotonic()
                val_result = self._validator.validate(raw_text, self.service_type)
                validation_time = time.monotonic() - t_val

                metadata = ServiceMetadata(
                    generation_id=generation_id,
                    service_type=self.service_type,
                    provider=self._config.provider,
                    model=self._engine.model_name,
                    prompt_name=loaded.metadata.name,
                    prompt_version=loaded.metadata.version,
                    response_time_seconds=round(response_time, 3),
                    validation_time_seconds=round(validation_time, 4),
                    retry_count=retry_count,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=(
                        usage.get("prompt_tokens", 0)
                        + usage.get("completion_tokens", 0)
                    ),
                )

                if not val_result.passed:
                    logger.warning(
                        "generation.%s: content validation failed: %s",
                        self.service_type.value,
                        val_result.errors,
                    )
                    METRICS.record_validation_failed(ValidationFailedEvent(
                        service_type=self.service_type.value,
                        generation_id=generation_id,
                        errors=tuple(val_result.errors),
                        warnings=tuple(val_result.warnings),
                        content_length=len(raw_text),
                    ))
                    METRICS.record_failed(GenerationFailedEvent(
                        service_type=self.service_type.value,
                        generation_id=generation_id,
                        log_id=log_id,
                        reason="validation_failed",
                        retry_count=retry_count,
                        errors=tuple(val_result.errors),
                    ))
                    return ServiceOutput(
                        success=False,
                        service_type=self.service_type,
                        content=raw_text,
                        errors=val_result.errors,
                        warnings=val_result.warnings,
                        metadata=metadata,
                    )

                logger.info(
                    "generation.%s: success %.2fs tokens=%d",
                    self.service_type.value,
                    response_time,
                    metadata.total_tokens,
                )
                METRICS.record_completed(GenerationCompletedEvent(
                    service_type=self.service_type.value,
                    generation_id=generation_id,
                    log_id=log_id,
                    model=self._engine.model_name,
                    response_time_seconds=round(response_time, 3),
                    validation_time_seconds=round(validation_time, 4),
                    retry_count=retry_count,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=metadata.total_tokens,
                ))
                return ServiceOutput(
                    success=True,
                    service_type=self.service_type,
                    content=raw_text,
                    errors=[],
                    warnings=val_result.warnings,
                    metadata=metadata,
                )

            except Exception as exc:
                last_error = str(exc)
                retry_count += 1

                if attempt < self._config.max_retries:
                    logger.warning(
                        "generation.%s: attempt %d failed (%s) — retry in %.1fs",
                        self.service_type.value,
                        attempt + 1,
                        last_error,
                        delay,
                    )
                    METRICS.record_retry(RetryStartedEvent(
                        service_type=self.service_type.value,
                        generation_id=generation_id,
                        attempt=attempt + 1,
                        max_attempts=self._config.max_retries + 1,
                        error=last_error,
                        delay_seconds=delay,
                    ))
                    time.sleep(delay)
                    delay *= self._config.retry_backoff
                else:
                    logger.error(
                        "generation.%s: all %d attempts failed — %s",
                        self.service_type.value,
                        self._config.max_retries + 1,
                        last_error,
                    )

        METRICS.record_failed(GenerationFailedEvent(
            service_type=self.service_type.value,
            generation_id=generation_id,
            log_id=log_id,
            reason="all_retries_exhausted",
            retry_count=retry_count,
            errors=(f"All {self._config.max_retries + 1} attempts failed. "
                    f"Last error: {last_error}",),
        ))
        return ServiceOutput.failure(
            service_type=self.service_type,
            errors=[
                f"All {self._config.max_retries + 1} attempts failed. "
                f"Last error: {last_error}"
            ],
        )

    # ── Shared log formatting helpers ─────────────────────────────────────────

    @staticmethod
    def _fmt_dict(d: dict | None, indent: int = 0) -> str:
        """Format a dict as indented key: value lines."""
        if not d:
            return "  (none)"
        prefix = "  " * (indent + 1)
        lines = []
        for k, v in d.items():
            if v is None or v == "" or v == [] or v == {}:
                continue
            if isinstance(v, dict):
                lines.append(f"{prefix}{k}:")
                lines.append(BaseAIService._fmt_dict(v, indent + 1))
            elif isinstance(v, list):
                items = ", ".join(str(i) for i in v if i)
                if items:
                    lines.append(f"{prefix}{k}: {items}")
            else:
                lines.append(f"{prefix}{k}: {v}")
        return "\n".join(lines) if lines else "  (none)"
