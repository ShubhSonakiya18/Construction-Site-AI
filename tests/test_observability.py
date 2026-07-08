"""
tests/test_observability.py — Unit tests for Sprint 5.1 observability layer.

Tests cover:
  Timer:
    - elapsed is 0.0 before start
    - elapsed > 0 after stop
    - context manager usage
    - is_running property
    - explicit start/stop
    - stop before start raises RuntimeError

  Events (dataclasses):
    - Immutability (frozen=True)
    - event_type field is set automatically
    - timestamp is a UTC datetime
    - Default field values

  GenerationMetrics:
    - record_started increments total_started
    - record_completed increments total_succeeded and accumulates tokens/time
    - record_failed increments total_failed
    - record_retry does not crash
    - record_validation_failed increments bucket.validation_failures
    - record_cache_hit / record_cache_miss track counts
    - summary() structure and computed fields
    - reset() clears all state
    - METRICS global is the singleton
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from generation.observability import METRICS, GenerationMetrics, Timer
from generation.observability.events import (
    GenerationCompletedEvent,
    GenerationFailedEvent,
    GenerationStartedEvent,
    PromptCacheHitEvent,
    PromptCacheMissEvent,
    RetryStartedEvent,
    ValidationFailedEvent,
)


# ── Timer ─────────────────────────────────────────────────────────────────────

class TestTimer:
    def test_elapsed_zero_before_start(self):
        t = Timer()
        assert t.elapsed == 0.0

    def test_is_running_false_before_start(self):
        t = Timer()
        assert t.is_running is False

    def test_start_sets_is_running_true(self):
        t = Timer()
        t.start()
        assert t.is_running is True

    def test_stop_sets_is_running_false(self):
        t = Timer()
        t.start()
        t.stop()
        assert t.is_running is False

    def test_elapsed_positive_after_stop(self):
        t = Timer()
        t.start()
        time.sleep(0.05)  # 50ms: reliably above one monotonic tick on Windows
        elapsed = t.stop()
        assert elapsed > 0.0
        assert t.elapsed > 0.0

    def test_elapsed_while_running_is_live(self):
        t = Timer()
        t.start()
        e1 = t.elapsed
        time.sleep(0.05)
        e2 = t.elapsed
        assert e2 > e1

    def test_context_manager_start_and_stop(self):
        with Timer() as t:
            time.sleep(0.05)
        assert t.elapsed > 0.0
        assert t.is_running is False

    def test_context_manager_returns_timer_instance(self):
        with Timer() as t:
            assert isinstance(t, Timer)

    def test_stop_before_start_raises_runtime_error(self):
        t = Timer()
        with pytest.raises(RuntimeError, match="before Timer.start"):
            t.stop()

    def test_start_returns_self_for_chaining(self):
        t = Timer()
        result = t.start()
        assert result is t

    def test_repr_shows_elapsed_when_stopped(self):
        t = Timer()
        t.start()
        t.stop()
        r = repr(t)
        assert "Timer(" in r
        assert "s)" in r

    def test_repr_shows_running_when_active(self):
        t = Timer()
        t.start()
        r = repr(t)
        assert "running" in r


# ── Events ────────────────────────────────────────────────────────────────────

class TestEvents:
    def test_generation_started_event_type(self):
        e = GenerationStartedEvent(service_type="daily_report", generation_id="id-1")
        assert e.event_type == "generation.started"

    def test_generation_completed_event_type(self):
        e = GenerationCompletedEvent(service_type="daily_report", generation_id="id-1")
        assert e.event_type == "generation.completed"

    def test_generation_failed_event_type(self):
        e = GenerationFailedEvent(service_type="daily_report", generation_id="id-1", reason="all_retries_exhausted")
        assert e.event_type == "generation.failed"

    def test_retry_started_event_type(self):
        e = RetryStartedEvent(service_type="daily_report", generation_id="id-1")
        assert e.event_type == "retry.started"

    def test_validation_failed_event_type(self):
        e = ValidationFailedEvent(service_type="daily_report", generation_id="id-1")
        assert e.event_type == "validation.failed"

    def test_cache_hit_event_type(self):
        e = PromptCacheHitEvent(prompt_name="daily_report")
        assert e.event_type == "prompt.cache_hit"

    def test_cache_miss_event_type(self):
        e = PromptCacheMissEvent(prompt_name="daily_report")
        assert e.event_type == "prompt.cache_miss"

    def test_events_are_frozen(self):
        """Events are immutable."""
        e = GenerationStartedEvent(service_type="x", generation_id="y")
        with pytest.raises((TypeError, AttributeError)):
            e.service_type = "mutated"  # type: ignore[misc]

    def test_event_timestamp_is_utc_datetime(self):
        e = GenerationStartedEvent()
        assert isinstance(e.timestamp, datetime)
        assert e.timestamp.tzinfo is not None

    def test_generation_completed_defaults(self):
        e = GenerationCompletedEvent(service_type="s", generation_id="g")
        assert e.total_tokens == 0
        assert e.retry_count == 0
        assert e.response_time_seconds == 0.0

    def test_validation_failed_errors_are_tuple(self):
        e = ValidationFailedEvent(
            service_type="s",
            generation_id="g",
            errors=("error 1", "error 2"),
        )
        assert isinstance(e.errors, tuple)
        assert len(e.errors) == 2


# ── GenerationMetrics ─────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset METRICS before each test to avoid cross-test pollution."""
    METRICS.reset()
    yield
    METRICS.reset()


class TestGenerationMetricsCounters:
    def test_initial_totals_are_zero(self):
        m = GenerationMetrics()
        assert m.total_succeeded == 0
        assert m.total_failed == 0

    def test_record_started_increments_total_started(self):
        m = GenerationMetrics()
        m.record_started(GenerationStartedEvent(service_type="daily_report", generation_id="g1"))
        summary = m.summary()
        assert summary["totals"]["started"] == 1

    def test_record_completed_increments_succeeded(self):
        m = GenerationMetrics()
        m.record_completed(GenerationCompletedEvent(
            service_type="daily_report",
            generation_id="g1",
            total_tokens=100,
            response_time_seconds=0.5,
        ))
        assert m.total_succeeded == 1

    def test_record_failed_increments_failed(self):
        m = GenerationMetrics()
        m.record_failed(GenerationFailedEvent(
            service_type="daily_report",
            generation_id="g1",
            reason="all_retries_exhausted",
        ))
        assert m.total_failed == 1

    def test_record_completed_accumulates_tokens(self):
        m = GenerationMetrics()
        for tokens in [100, 200, 150]:
            m.record_completed(GenerationCompletedEvent(
                service_type="daily_report",
                generation_id="g",
                total_tokens=tokens,
            ))
        summary = m.summary()
        assert summary["per_service"]["daily_report"]["total_tokens"] == 450

    def test_record_cache_hit_increments_hits(self):
        m = GenerationMetrics()
        m.record_cache_hit(PromptCacheHitEvent(prompt_name="daily_report"))
        m.record_cache_hit(PromptCacheHitEvent(prompt_name="safety_talk"))
        summary = m.summary()
        assert summary["cache"]["hits"] == 2

    def test_record_cache_miss_increments_misses(self):
        m = GenerationMetrics()
        m.record_cache_miss(PromptCacheMissEvent(prompt_name="daily_report"))
        summary = m.summary()
        assert summary["cache"]["misses"] == 1

    def test_cache_hit_rate_computed_correctly(self):
        m = GenerationMetrics()
        m.record_cache_hit(PromptCacheHitEvent(prompt_name="a"))
        m.record_cache_hit(PromptCacheHitEvent(prompt_name="b"))
        m.record_cache_miss(PromptCacheMissEvent(prompt_name="c"))
        # 2 hits, 1 miss → rate = 2/3
        assert abs(m.cache_hit_rate - round(2 / 3, 3)) < 0.001

    def test_record_retry_does_not_crash(self):
        m = GenerationMetrics()
        m.record_retry(RetryStartedEvent(
            service_type="daily_report",
            generation_id="g1",
            attempt=1,
            max_attempts=3,
        ))

    def test_record_validation_failed_increments_bucket(self):
        m = GenerationMetrics()
        m.record_validation_failed(ValidationFailedEvent(
            service_type="customer_update",
            generation_id="g1",
            errors=("Too short",),
        ))
        summary = m.summary()
        assert summary["per_service"]["customer_update"]["validation_failures"] == 1

    def test_per_service_success_rate(self):
        m = GenerationMetrics()
        m.record_completed(GenerationCompletedEvent(service_type="safety_talk", generation_id="g1"))
        m.record_completed(GenerationCompletedEvent(service_type="safety_talk", generation_id="g2"))
        m.record_failed(GenerationFailedEvent(
            service_type="safety_talk", generation_id="g3", reason="validation_failed"
        ))
        summary = m.summary()
        sr = summary["per_service"]["safety_talk"]["success_rate"]
        # 2 success / 3 total = 0.667
        assert abs(sr - round(2 / 3, 3)) < 0.001


class TestGenerationMetricsSummary:
    def test_summary_structure(self):
        m = GenerationMetrics()
        s = m.summary()
        assert "totals" in s
        assert "cache" in s
        assert "per_service" in s

    def test_summary_totals_structure(self):
        m = GenerationMetrics()
        totals = m.summary()["totals"]
        assert "started" in totals
        assert "succeeded" in totals
        assert "failed" in totals
        assert "success_rate" in totals

    def test_summary_cache_structure(self):
        m = GenerationMetrics()
        cache = m.summary()["cache"]
        assert "hits" in cache
        assert "misses" in cache
        assert "hit_rate" in cache

    def test_summary_per_service_avg_response_time(self):
        m = GenerationMetrics()
        m.record_completed(GenerationCompletedEvent(
            service_type="daily_report", generation_id="g1",
            response_time_seconds=1.0, total_tokens=100,
        ))
        m.record_completed(GenerationCompletedEvent(
            service_type="daily_report", generation_id="g2",
            response_time_seconds=3.0, total_tokens=100,
        ))
        summary = m.summary()
        avg = summary["per_service"]["daily_report"]["avg_response_time_seconds"]
        assert avg == 2.0

    def test_avg_response_time_zero_when_no_successes(self):
        m = GenerationMetrics()
        m.record_failed(GenerationFailedEvent(
            service_type="daily_report", generation_id="g1", reason="exhausted"
        ))
        summary = m.summary()
        # No succeeded → no avg
        assert summary["per_service"]["daily_report"]["avg_response_time_seconds"] == 0.0

    def test_success_rate_zero_when_no_completions(self):
        m = GenerationMetrics()
        s = m.summary()
        assert s["totals"]["success_rate"] == 0.0

    def test_cache_hit_rate_zero_when_no_cache_events(self):
        m = GenerationMetrics()
        s = m.summary()
        assert s["cache"]["hit_rate"] == 0.0


class TestGenerationMetricsReset:
    def test_reset_clears_totals(self):
        m = GenerationMetrics()
        m.record_completed(GenerationCompletedEvent(
            service_type="daily_report", generation_id="g1", total_tokens=50
        ))
        m.reset()
        assert m.total_succeeded == 0
        assert m.total_failed == 0

    def test_reset_clears_cache_counts(self):
        m = GenerationMetrics()
        m.record_cache_hit(PromptCacheHitEvent(prompt_name="x"))
        m.reset()
        s = m.summary()
        assert s["cache"]["hits"] == 0
        assert s["cache"]["misses"] == 0

    def test_reset_clears_per_service_buckets(self):
        m = GenerationMetrics()
        m.record_completed(GenerationCompletedEvent(
            service_type="daily_report", generation_id="g1", total_tokens=100
        ))
        m.reset()
        s = m.summary()
        assert s["per_service"] == {}


class TestGlobalMetricsSingleton:
    def test_metrics_is_generation_metrics_instance(self):
        assert isinstance(METRICS, GenerationMetrics)

    def test_metrics_records_and_resets(self):
        METRICS.record_started(GenerationStartedEvent(service_type="x", generation_id="y"))
        assert METRICS.summary()["totals"]["started"] == 1
        METRICS.reset()
        assert METRICS.summary()["totals"]["started"] == 0
