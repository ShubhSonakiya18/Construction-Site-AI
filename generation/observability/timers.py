"""
timers.py — Timer: lightweight elapsed-time context manager.

Why a dedicated timer (not inline time.monotonic() pairs):
    Inline timing requires two variables (t_start, t_end) and mental bookkeeping
    around exceptions. A context manager localises the timing concern and works
    correctly even if the body raises — elapsed is always set on __exit__.

    The base_service.py generation loop already uses inline timing for response_time
    and validation_time. Sprint 5.1 introduces Timer so that future code (and the
    manager's total-elapsed measurement) uses a consistent, testable abstraction.

Usage:
    from generation.observability.timers import Timer

    with Timer() as t:
        result = service.generate(log)
    print(f"Elapsed: {t.elapsed:.3f}s")

    # Timer is also usable without context manager for one-shot timing:
    t = Timer()
    t.start()
    do_something()
    t.stop()
    print(t.elapsed)
"""
from __future__ import annotations

import time


class Timer:
    """Measures wall-clock elapsed time using time.monotonic().

    Attributes:
        elapsed: Seconds elapsed between start() and stop() (or __exit__).
                 0.0 if stop() has not been called yet.
        is_running: True while the timer is active.
    """

    def __init__(self) -> None:
        self._start: float | None = None
        self._end: float | None = None

    # ── Context manager API ───────────────────────────────────────────────────

    def __enter__(self) -> "Timer":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    # ── Explicit API ──────────────────────────────────────────────────────────

    def start(self) -> "Timer":
        """Start (or restart) the timer. Returns self for chaining."""
        self._start = time.monotonic()
        self._end = None
        return self

    def stop(self) -> float:
        """Stop the timer. Returns elapsed seconds."""
        if self._start is None:
            raise RuntimeError("Timer.stop() called before Timer.start()")
        self._end = time.monotonic()
        return self.elapsed

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def elapsed(self) -> float:
        """Elapsed seconds. Snapshotted at stop(); live if still running."""
        if self._start is None:
            return 0.0
        end = self._end if self._end is not None else time.monotonic()
        return round(end - self._start, 6)

    @property
    def is_running(self) -> bool:
        return self._start is not None and self._end is None

    def __repr__(self) -> str:
        status = "running" if self.is_running else f"{self.elapsed:.3f}s"
        return f"Timer({status})"
