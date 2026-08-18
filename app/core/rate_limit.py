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

from fastapi import Depends, HTTPException, status

from app.api.dependencies import get_app_settings
from app.core.config import Settings


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


class RedisRateLimiter:
    """Redis-backed sliding-window rate limiter — the ADR-041 migration,
    delivered in Sprint 9 now that Redis is already required infrastructure
    (celery_app.py). Implements the identical RateLimiter Protocol as
    MemoryRateLimiter; every existing caller (AuthService,
    enforce_ai_generation_rate_limit()) needed zero changes.

    Solves MemoryRateLimiter's documented multi-worker limitation: counters
    live in Redis, shared across every uvicorn worker process (and every
    Celery worker, if one ever needed to rate-limit something), and survive
    a process restart — a real production deployment with `--workers N`
    now has ONE limit, not N independent ones.

    Algorithm — a Redis sorted set per key, member=unique per-attempt
    token, score=attempt timestamp (matches ADR-041's specified shape):
        ZADD key timestamp member       — record this attempt
        ZREMRANGEBYSCORE key 0 cutoff   — prune attempts outside the window
        ZCARD key                       — count what's left
        EXPIRE key window_seconds       — let Redis reclaim an idle key
                                           itself; no unbounded key growth
                                           for buckets that stop being hit,
                                           mirroring MemoryRateLimiter's own
                                           in-place pruning on every check()
    Uses a Lua script (EVAL) so the four Redis commands run atomically as
    one round-trip — without it, two concurrent requests for the same key
    could both read a stale ZCARD before either's ZADD lands, letting
    limit+1 or more through under load. MemoryRateLimiter gets the
    equivalent atomicity from its in-process threading.Lock; a Lua script
    is the Redis-native way to get the same guarantee across processes.
    """

    _LUA_CHECK = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local window = tonumber(ARGV[2])
        local limit = tonumber(ARGV[3])
        local member = ARGV[4]

        redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
        local count = redis.call('ZCARD', key)
        if count >= limit then
            return 0
        end
        redis.call('ZADD', key, now, member)
        redis.call('EXPIRE', key, window)
        return 1
    """

    def __init__(self, redis_url: str) -> None:
        import redis as redis_lib

        self._client = redis_lib.Redis.from_url(redis_url, decode_responses=True)
        self._check_script = self._client.register_script(self._LUA_CHECK)

    def check(self, key: str, *, limit: int, window_seconds: int) -> bool:
        import time
        import uuid

        now = time.time()
        # A unique member per call (not just the timestamp) — two attempts
        # in the same millisecond would otherwise collide as the same
        # sorted-set member and silently count as one, under-counting real
        # attempts. MemoryRateLimiter has no equivalent hazard: it appends
        # to a plain list, where duplicate values are never merged.
        member = f"{now}:{uuid.uuid4().hex}"
        allowed = self._check_script(
            keys=[f"ratelimit:{key}"], args=[now, window_seconds, limit, member],
        )
        return bool(allowed)

    def reset(self, key: str) -> None:
        """Clear all recorded attempts for `key` — same contract as
        MemoryRateLimiter.reset()."""
        self._client.delete(f"ratelimit:{key}")


# Process-wide singleton — mirrors app/core/config.py's get_settings()
# lru_cache pattern (one shared instance per process, not per-request).
# Populated lazily by get_rate_limiter() below (needs Settings to know
# which implementation and, for Redis, which URL — unlike the module load
# time this used to be built at, before Settings was in the picture).
_rate_limiter: RateLimiter | None = None


def get_rate_limiter(settings: Settings = Depends(get_app_settings)) -> RateLimiter:
    """Return the process-wide RateLimiter instance, building it on first
    call: RedisRateLimiter, using settings.redis_rate_limit_url.

    A plain default-arg `settings=None` here (instead of the real
    Depends(get_app_settings) below) would be silently wrong under
    FastAPI: an untyped, non-Depends parameter on a dependency function
    is NOT injected — FastAPI would try to bind it as a query parameter
    instead, and this function would then build a MemoryRateLimiter
    (settings staying None) for every real request, quietly reverting the
    whole Sprint 9 migration in production while every test that passes
    Settings directly kept working. Depends(get_app_settings) is what
    makes `Depends(get_rate_limiter)` in a router actually receive the
    app's real Settings — the same pattern app/services/email_sender.py's
    get_email_sender() already established.

    Use as a FastAPI dependency (Depends(get_rate_limiter)) or call
    directly with a Settings instance (e.g. get_rate_limiter(settings)) —
    callers depend only on the RateLimiter protocol, never on which
    concrete class is behind it (ADR-041).
    """
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RedisRateLimiter(settings.redis_rate_limit_url)
    return _rate_limiter


def reset_rate_limiter() -> None:
    """Clear the cached singleton — test isolation only, mirrors
    database.session.reset_engine()'s purpose. Without this, the first
    test in a pytest process to call get_rate_limiter() would permanently
    decide every later test's RateLimiter implementation."""
    global _rate_limiter
    _rate_limiter = None


def enforce_ai_generation_rate_limit(
    rate_limiter: RateLimiter, *, user_id, settings
) -> None:
    """Shared 429 guard for every endpoint that spends the shared Groq
    quota per HTTP request: POST /daily-logs/{id}/generate and POST
    /projects/{id}/ask. Both call this identically rather than duplicating
    the check/raise pair, so a third Groq-calling endpoint added later
    only needs one call, not a copy-pasted block.

    Raises HTTPException(429) if user_id has exceeded
    Settings.rate_limit_ai_generation_attempts within
    Settings.rate_limit_ai_generation_window_seconds. Keyed per-user, not
    per-company: this throttles one actor hammering the endpoint, not the
    company's total Groq spend — see Settings.rate_limit_ai_generation_attempts
    docstring for why a company-wide budget cap is explicitly out of scope
    here.

    """
    if not rate_limiter.check(
        f"ai_generation:{user_id}",
        limit=settings.rate_limit_ai_generation_attempts,
        window_seconds=settings.rate_limit_ai_generation_window_seconds,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many AI generation requests. Please try again later.",
        )
