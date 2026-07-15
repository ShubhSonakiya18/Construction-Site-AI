"""
app/core/rate_limit.py — RateLimiter protocol + in-memory implementation.

Sprint 8, Subsystem 5 (Security Hardening). Explicit user requirement:
rate limiting must be behind an abstraction so a future Redis-backed
implementation can replace MemoryRateLimiter without touching any
router or service that calls it. See docs/DECISIONS.md for the full
migration-path writeup.

Why a Protocol, not an ABC:
    RateLimiter has exactly one method or a small handful of them — a
    structural (duck-typed) interface via typing.Protocol is enough to
    get static type-checking on call sites without forcing every future
    implementation to inherit from a base class. This matches
    extraction/engines/base_engine.py's BaseLLMProvider precedent in
    spirit (an abstraction the concrete implementation is swapped
    behind) but Protocol is the lighter-weight tool when there's no
    shared implementation to inherit, only a shared shape.

Why MemoryRateLimiter is correct for Sprint 8, and its documented limits:
    - Zero new infrastructure: no Redis, no new migration, consistent
      with this project's "no paid services, minimal new infra per
      sprint" posture (docs/HANDOVER.md §2).
    - Real limitation: state is per-process. A multi-worker uvicorn
      deployment (`--workers N`) would have N independent counters, so
      the effective limit is N times the configured value, and a
      restart clears all counters. This is an accepted, DOCUMENTED gap
      at this project's current target scale (docs/DECISIONS.md
      multi-tenancy notes: hundreds of companies, not a
      multi-region/multi-worker production deployment yet) — not an
      oversight. See docs/DECISIONS.md for the exact migration trigger
      and the RedisRateLimiter shape that will replace this.
    - Thread-safety: a single lock guards the shared bucket dict.
      FastAPI route handlers here are sync (see app/api/dependencies.py
      get_db() docstring on threadpool offload), so concurrent requests
      genuinely run on different threads within one process and a lock
      is required, not optional.

Algorithm: sliding-window log (store attempt timestamps, prune anything
older than the window on each check). Chosen over a fixed-window counter
because a fixed window allows a burst of 2x the limit at the window
boundary (e.g. limit=5/60s lets 5 requests at 0:59 and 5 more at 1:01);
a sliding window doesn't have that edge case. Chosen over a token-bucket
because the limits here (login attempts, password reset requests) are
about "how many times in the last N minutes," which a sliding window
expresses directly, rather than a refill-rate concept.
"""
from __future__ import annotations

import threading
import time
from typing import Protocol


class RateLimiter(Protocol):
    """Structural interface every rate limiter implementation satisfies.

    A future RedisRateLimiter (Sprint 9+) implements this exact method
    with a Redis sorted-set (ZADD/ZREMRANGEBYSCORE/ZCARD) instead of an
    in-process dict — see docs/DECISIONS.md for the planned shape. No
    caller (AuthService, any router) needs to change when that swap
    happens; only the object constructed in app/core/config.py or
    app/create_app.py's dependency wiring changes.
    """

    def check(self, key: str, *, limit: int, window_seconds: int) -> bool:
        """Return True if the action identified by `key` is allowed right
        now (and record this attempt), False if `limit` attempts have
        already occurred within the last `window_seconds`.

        `key` is caller-defined and should encode both the action and
        the actor, e.g. f"login:{email}" or f"login:ip:{ip_address}" —
        this module has no opinion on what a "key" represents, only on
        counting occurrences of it within a time window.
        """
        ...


class MemoryRateLimiter:
    """In-process, thread-safe sliding-window rate limiter.

    See module docstring for the documented single-process limitation
    and the planned Redis migration path.
    """

    def __init__(self) -> None:
        self._buckets: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, *, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.setdefault(key, [])
            cutoff = now - window_seconds
            # Prune expired entries in place so the dict doesn't grow
            # unbounded for a key that's checked repeatedly over a long
            # process lifetime.
            bucket[:] = [t for t in bucket if t > cutoff]
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True

    def reset(self, key: str) -> None:
        """Clear all recorded attempts for `key`. Used where a successful
        action should immediately un-throttle a key rather than waiting
        out the window (e.g. a successful login resetting the per-email
        login-attempt bucket, mirroring the account-lockout counter's own
        reset-on-success behavior)."""
        with self._lock:
            self._buckets.pop(key, None)


# Process-wide singleton — mirrors app/core/config.py's get_settings()
# lru_cache pattern (one shared instance per process, not per-request).
# A future RedisRateLimiter would similarly be constructed once and
# shared, backed by a real connection pool instead of an in-memory dict.
_rate_limiter: RateLimiter = MemoryRateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Return the process-wide RateLimiter instance.

    Use as a FastAPI dependency (Depends(get_rate_limiter)) or call
    directly from a service — the concrete type is a MemoryRateLimiter in
    Sprint 8; callers depend only on the RateLimiter protocol.
    """
    return _rate_limiter
