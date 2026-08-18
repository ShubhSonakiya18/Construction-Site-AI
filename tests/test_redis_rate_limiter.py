"""
tests/test_redis_rate_limiter.py — Sprint 9: RedisRateLimiter (ADR-041 migration).

Requires a real Redis instance reachable at the URL below — this project
runs one via Docker for local dev (docs/BACKEND_STARTUP.md §4.5). Skipped
automatically if Redis isn't reachable, so CI/dev machines without Redis
running don't fail the whole suite — same pattern as
tests/test_extraction_pipeline.py's HAS_GROQ gate for the one test that
needs a real external service.

Uses Redis logical DB 15 (unused elsewhere in this project's DB-0/1/2
convention — see app/core/config.py) and flushes only that DB before/after
each test, never touching DB 0/1/2 where the real broker/backend/rate-limit
data could be running concurrently in dev.
"""
from __future__ import annotations

import time

import pytest

_TEST_REDIS_URL = "redis://localhost:6379/15"


def _redis_available() -> bool:
    try:
        import redis as redis_lib

        client = redis_lib.Redis.from_url(_TEST_REDIS_URL, socket_connect_timeout=1)
        return client.ping()
    except Exception:
        return False


HAS_REDIS = _redis_available()

pytestmark = pytest.mark.skipif(not HAS_REDIS, reason="Redis not reachable at localhost:6379")


@pytest.fixture
def limiter():
    from app.core.rate_limit import RedisRateLimiter

    rl = RedisRateLimiter(_TEST_REDIS_URL)
    rl._client.flushdb()
    yield rl
    rl._client.flushdb()


class TestRedisRateLimiterBasics:
    def test_allows_first_attempt(self, limiter):
        assert limiter.check("test:key1", limit=3, window_seconds=60) is True

    def test_allows_up_to_limit(self, limiter):
        for _ in range(5):
            assert limiter.check("test:key2", limit=5, window_seconds=60) is True

    def test_blocks_after_limit_reached(self, limiter):
        for _ in range(3):
            limiter.check("test:key3", limit=3, window_seconds=60)
        assert limiter.check("test:key3", limit=3, window_seconds=60) is False

    def test_different_keys_have_independent_buckets(self, limiter):
        for _ in range(3):
            limiter.check("test:key4a", limit=3, window_seconds=60)
        assert limiter.check("test:key4a", limit=3, window_seconds=60) is False
        assert limiter.check("test:key4b", limit=3, window_seconds=60) is True

    def test_window_expiry_allows_new_attempts(self, limiter):
        for _ in range(2):
            limiter.check("test:key5", limit=2, window_seconds=1)
        assert limiter.check("test:key5", limit=2, window_seconds=1) is False
        time.sleep(1.2)
        assert limiter.check("test:key5", limit=2, window_seconds=1) is True

    def test_reset_clears_the_bucket(self, limiter):
        for _ in range(3):
            limiter.check("test:key6", limit=3, window_seconds=60)
        assert limiter.check("test:key6", limit=3, window_seconds=60) is False
        limiter.reset("test:key6")
        assert limiter.check("test:key6", limit=3, window_seconds=60) is True


class TestRedisRateLimiterAtomicity:
    def test_concurrent_checks_never_exceed_limit(self, limiter):
        """The Lua-script atomicity this class exists for: without it, N
        concurrent requests racing the same key could all read a stale
        ZCARD before any ZADD lands, letting more than `limit` through.
        Runs real concurrent requests against real Redis (threads, not
        asyncio, since redis-py's sync client is what RedisRateLimiter
        uses) to catch a regression a single-threaded test cannot."""
        import concurrent.futures

        limit = 10
        results = []

        def attempt():
            return limiter.check("test:concurrent", limit=limit, window_seconds=60)

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(attempt) for _ in range(30)]
            results = [f.result() for f in futures]

        assert results.count(True) == limit
        assert results.count(False) == 30 - limit


class TestRedisRateLimiterProtocolCompliance:
    def test_satisfies_ratelimiter_protocol(self, limiter):
        """RateLimiter is a structural (not @runtime_checkable) Protocol,
        so this asserts the shape directly rather than via isinstance()."""
        assert callable(limiter.check)
        assert limiter.check("shape-check", limit=1, window_seconds=60) is True

    def test_same_behavior_shape_as_memory_rate_limiter(self):
        """Both implementations must be interchangeable — the whole point
        of ADR-041's Protocol design. Runs the identical scenario against
        both and asserts identical outcomes."""
        from app.core.rate_limit import MemoryRateLimiter, RedisRateLimiter

        redis_limiter = RedisRateLimiter(_TEST_REDIS_URL)
        redis_limiter._client.flushdb()
        memory_limiter = MemoryRateLimiter()

        redis_results = [
            redis_limiter.check("shape-test", limit=3, window_seconds=60) for _ in range(5)
        ]
        memory_results = [
            memory_limiter.check("shape-test", limit=3, window_seconds=60) for _ in range(5)
        ]

        assert redis_results == memory_results == [True, True, True, False, False]
        redis_limiter._client.flushdb()


class TestGetRateLimiterWiring:
    def test_get_rate_limiter_builds_redis_backed_instance_from_settings(self):
        """Confirms app/core/rate_limit.py's get_rate_limiter() dependency
        actually builds a RedisRateLimiter when given real Settings — the
        exact wiring bug this test file's docstring warns a plain
        `settings=None` default would have silently defeated in
        production (see get_rate_limiter()'s own docstring)."""
        from app.core.config import Settings
        from app.core.rate_limit import RedisRateLimiter, get_rate_limiter, reset_rate_limiter

        reset_rate_limiter()
        settings = Settings(redis_rate_limit_url=_TEST_REDIS_URL, _env_file=None)
        try:
            rl = get_rate_limiter(settings)
            assert isinstance(rl, RedisRateLimiter)
        finally:
            reset_rate_limiter()
