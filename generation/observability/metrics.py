"""
metrics.py — GenerationMetrics: in-memory metrics accumulator.

Why in-memory (not a DB write or external push):
    Sprint 5.1 introduces the *foundation* for observability. Pushing metrics to
    external systems (Prometheus, Grafana, Datadog) requires Sprint 7's async
    infrastructure (Celery, Redis). Recording metrics in a thread-safe in-memory
    structure now means Sprint 7 can wire persistence with zero API changes.

    The METRICS global is process-scoped. In production (Sprint 7 Celery workers),
    each worker process has its own METRICS; aggregation across workers happens in
    Sprint 7's admin dashboard. For the Sprint 5 CLI (single-process), METRICS
    captures one full run.

Thread safety:
    Python's GIL makes individual dict and list operations atomic. For the CLI
    (single thread) and early multi-service use this is sufficient. Sprint 7 adds
    explicit locking when Celery workers share state.

Tracked metrics:
    - Per-service generation counts (success / failure)
    - Total and per-service token usage
    - Total and per-service response times
    - Retry counts
    - Validation failure counts
    - Prompt cache hit/miss counts
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from generation.observability.events import (
    GenerationCompletedEvent,
    GenerationFailedEvent,
    GenerationStartedEvent,
    PromptCacheHitEvent,
    PromptCacheMissEvent,
    RetryCompletedEvent,
    RetryStartedEvent,
    ValidationFailedEvent,
)

logger = logging.getLogger(__name__)


@dataclass
class ServiceMetricsBucket:
    """Per-service metric counters."""

    generations_started: int = 0
    generations_succeeded: int = 0
    generations_failed: int = 0
    total_tokens: int = 0
    total_response_time: float = 0.0
    total_retries: int = 0
    validation_failures: int = 0


class GenerationMetrics:
    """In-memory accumulator for generation observability metrics.

    Usage:
        METRICS.record_started(event)
        METRICS.record_completed(event)
        summary = METRICS.summary()
        METRICS.reset()
    """

    def __init__(self) -> None:
        self._buckets: dict[str, ServiceMetricsBucket] = defaultdict(ServiceMetricsBucket)
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._total_started: int = 0
        self._total_succeeded: int = 0
        self._total_failed: int = 0

    # ── Event recorders ───────────────────────────────────────────────────────

    def record_started(self, event: GenerationStartedEvent) -> None:
        self._total_started += 1
        self._buckets[event.service_type].generations_started += 1
        logger.debug("metrics: generation.started service=%s id=%s",
                     event.service_type, event.generation_id)

    def record_completed(self, event: GenerationCompletedEvent) -> None:
        self._total_succeeded += 1
        bucket = self._buckets[event.service_type]
        bucket.generations_succeeded += 1
        bucket.total_tokens += event.total_tokens
        bucket.total_response_time += event.response_time_seconds
        bucket.total_retries += event.retry_count
        logger.debug("metrics: generation.completed service=%s tokens=%d rt=%.2fs",
                     event.service_type, event.total_tokens, event.response_time_seconds)

    def record_failed(self, event: GenerationFailedEvent) -> None:
        self._total_failed += 1
        bucket = self._buckets[event.service_type]
        bucket.generations_failed += 1
        bucket.total_retries += event.retry_count
        logger.debug("metrics: generation.failed service=%s reason=%s",
                     event.service_type, event.reason)

    def record_retry(self, event: RetryStartedEvent) -> None:
        logger.debug("metrics: retry.started service=%s attempt=%d/%d",
                     event.service_type, event.attempt, event.max_attempts)

    def record_retry_completed(self, event: RetryCompletedEvent) -> None:
        logger.debug("metrics: retry.completed service=%s attempt=%d",
                     event.service_type, event.attempt)

    def record_validation_failed(self, event: ValidationFailedEvent) -> None:
        self._buckets[event.service_type].validation_failures += 1
        logger.debug("metrics: validation.failed service=%s errors=%d",
                     event.service_type, len(event.errors))

    def record_cache_hit(self, event: PromptCacheHitEvent) -> None:
        self._cache_hits += 1
        logger.debug("metrics: prompt.cache_hit name=%s", event.prompt_name)

    def record_cache_miss(self, event: PromptCacheMissEvent) -> None:
        self._cache_misses += 1
        logger.debug("metrics: prompt.cache_miss name=%s", event.prompt_name)

    # ── Aggregates ────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        """Return a dict snapshot of all current metrics."""
        per_service: dict[str, dict] = {}
        for stype, bucket in self._buckets.items():
            total_gens = bucket.generations_succeeded + bucket.generations_failed
            per_service[stype] = {
                "started": bucket.generations_started,
                "succeeded": bucket.generations_succeeded,
                "failed": bucket.generations_failed,
                "total_tokens": bucket.total_tokens,
                "total_retries": bucket.total_retries,
                "validation_failures": bucket.validation_failures,
                "avg_response_time_seconds": (
                    round(bucket.total_response_time / bucket.generations_succeeded, 3)
                    if bucket.generations_succeeded > 0 else 0.0
                ),
                "success_rate": (
                    round(bucket.generations_succeeded / total_gens, 3)
                    if total_gens > 0 else 0.0
                ),
            }

        total_completed = self._total_succeeded + self._total_failed
        cache_total = self._cache_hits + self._cache_misses
        return {
            "totals": {
                "started": self._total_started,
                "succeeded": self._total_succeeded,
                "failed": self._total_failed,
                "success_rate": (
                    round(self._total_succeeded / total_completed, 3)
                    if total_completed > 0 else 0.0
                ),
            },
            "cache": {
                "hits": self._cache_hits,
                "misses": self._cache_misses,
                "hit_rate": (
                    round(self._cache_hits / cache_total, 3)
                    if cache_total > 0 else 0.0
                ),
            },
            "per_service": per_service,
        }

    def reset(self) -> None:
        """Clear all accumulated metrics (useful in tests)."""
        self._buckets.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        self._total_started = 0
        self._total_succeeded = 0
        self._total_failed = 0

    # ── Convenience ───────────────────────────────────────────────────────────

    @property
    def total_succeeded(self) -> int:
        return self._total_succeeded

    @property
    def total_failed(self) -> int:
        return self._total_failed

    @property
    def cache_hit_rate(self) -> float:
        total = self._cache_hits + self._cache_misses
        return round(self._cache_hits / total, 3) if total > 0 else 0.0


# Process-scoped global metrics instance.
# Tests call METRICS.reset() in fixtures to avoid cross-test pollution.
METRICS = GenerationMetrics()
