"""
generation/observability — Lightweight local observability abstractions.

Sprint 5.1: Foundation only. No external systems, no Prometheus, no OpenTelemetry.
Future sprints will wire dashboards, alerting, and persistent storage to these
abstractions without changing the event/metric API.

Public API:
    from generation.observability import METRICS, Timer
    from generation.observability.events import GenerationStartedEvent, ...

Usage:
    with Timer() as t:
        result = service.generate(log)
    print(t.elapsed)  # seconds as float

    METRICS.record_generation_completed(generation_id, service_type, tokens, elapsed)
    summary = METRICS.summary()
"""

from generation.observability.metrics import METRICS, GenerationMetrics
from generation.observability.timers import Timer

__all__ = ["METRICS", "GenerationMetrics", "Timer"]
