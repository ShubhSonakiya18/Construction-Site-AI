"""
events.py — Typed event dataclasses for the generation observability pipeline.

Design principles:
    - Every event is a dataclass (not a dict) — typed, introspectable, serializable
    - Events carry only the data that is useful for debugging and monitoring
    - No PII: events never carry full prompts, full AI responses, or API keys
    - All timestamps are UTC datetimes
    - Events are immutable by convention (frozen=True)

Event taxonomy:
    Generation lifecycle:
        GenerationStartedEvent   — a service.generate() call has begun
        GenerationCompletedEvent — generate() returned success=True
        GenerationFailedEvent    — generate() returned success=False (all retries exhausted
                                   OR content validation failure)

    Retry lifecycle:
        RetryStartedEvent        — an attempt failed, a retry will be made
        RetryCompletedEvent      — a retry succeeded

    Validation:
        ValidationFailedEvent    — ContentValidator.validate() found errors

    Cache:
        PromptCacheHitEvent      — PromptLoader served from cache
        PromptCacheMissEvent     — PromptLoader read from disk

Future integrations (Sprint 7+):
    - Persist events to generation_events DB table
    - Emit to a message queue (Redis Streams) for async processing
    - Aggregate in Grafana/Kibana
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Generation lifecycle ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class GenerationStartedEvent:
    event_type: str = field(default="generation.started", init=False)
    service_type: str = ""
    generation_id: str = ""
    log_id: str = ""
    model: str = ""
    prompt_name: str = ""
    prompt_version: str = ""
    timestamp: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class GenerationCompletedEvent:
    event_type: str = field(default="generation.completed", init=False)
    service_type: str = ""
    generation_id: str = ""
    log_id: str = ""
    model: str = ""
    response_time_seconds: float = 0.0
    validation_time_seconds: float = 0.0
    retry_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    timestamp: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class GenerationFailedEvent:
    event_type: str = field(default="generation.failed", init=False)
    service_type: str = ""
    generation_id: str = ""
    log_id: str = ""
    reason: str = ""      # "validation_failed" | "all_retries_exhausted" | "exception"
    retry_count: int = 0
    errors: tuple[str, ...] = field(default_factory=tuple)
    timestamp: datetime = field(default_factory=_now)


# ── Retry lifecycle ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RetryStartedEvent:
    event_type: str = field(default="retry.started", init=False)
    service_type: str = ""
    generation_id: str = ""
    attempt: int = 0
    max_attempts: int = 0
    error: str = ""
    delay_seconds: float = 0.0
    timestamp: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class RetryCompletedEvent:
    event_type: str = field(default="retry.completed", init=False)
    service_type: str = ""
    generation_id: str = ""
    attempt: int = 0
    timestamp: datetime = field(default_factory=_now)


# ── Content validation ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ValidationFailedEvent:
    event_type: str = field(default="validation.failed", init=False)
    service_type: str = ""
    generation_id: str = ""
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    content_length: int = 0
    timestamp: datetime = field(default_factory=_now)


# ── Prompt cache ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PromptCacheHitEvent:
    event_type: str = field(default="prompt.cache_hit", init=False)
    prompt_name: str = ""
    prompt_version: str = ""
    timestamp: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class PromptCacheMissEvent:
    event_type: str = field(default="prompt.cache_miss", init=False)
    prompt_name: str = ""
    timestamp: datetime = field(default_factory=_now)
