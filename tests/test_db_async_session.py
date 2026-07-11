"""
tests/test_db_async_session.py — Tests for database.session's async engine/session path.

Scope: covers only the async session machinery added in Sprint 7
(get_async_session, get_async_engine, _to_async_url, reset_async_engine).
Does NOT test repositories against an async session — see
database/session.py module docstring and docs/BACKEND_ARCHITECTURE.md for
why repositories remain sync-only. These tests exercise raw SQLAlchemy Core
usage (the supported use case for the async path).

WHY aiosqlite in-memory (not a live PostgreSQL) for these tests:
    Same rationale as the rest of the Sprint 6 test suite — zero
    infrastructure, sub-second setup, portable CI. aiosqlite is the async
    counterpart to the sqlite3 driver used by the sync in-memory tests.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from database.config import DatabaseConfig
from database.session import (
    _to_async_url,
    get_async_engine,
    get_async_session,
    reset_async_engine,
)


# ── _to_async_url() — pure function, no DB needed ────────────────────────────

class TestToAsyncUrl:
    def test_postgresql_scheme_rewritten(self):
        assert _to_async_url("postgresql://u:p@host:5432/db") == (
            "postgresql+asyncpg://u:p@host:5432/db"
        )

    def test_postgres_short_scheme_rewritten(self):
        assert _to_async_url("postgres://u:p@host:5432/db") == (
            "postgresql+asyncpg://u:p@host:5432/db"
        )

    def test_psycopg2_scheme_rewritten(self):
        assert _to_async_url("postgresql+psycopg2://u:p@host:5432/db") == (
            "postgresql+asyncpg://u:p@host:5432/db"
        )

    def test_sqlite_scheme_rewritten(self):
        assert _to_async_url("sqlite:///:memory:") == "sqlite+aiosqlite:///:memory:"

    def test_already_async_url_unchanged(self):
        assert _to_async_url("postgresql+asyncpg://u:p@host/db") == (
            "postgresql+asyncpg://u:p@host/db"
        )
        assert _to_async_url("sqlite+aiosqlite:///:memory:") == (
            "sqlite+aiosqlite:///:memory:"
        )


# ── get_async_engine() / get_async_session() — needs a real (in-memory) DB ──

@pytest.fixture(autouse=True)
async def _reset_async_singleton():
    """Ensure each test starts with a clean async engine singleton.

    Sprint 6's reset_engine() only touches the sync singleton — this fixture
    is the async equivalent, run before and after every test in this module
    so tests never leak engine state into each other.
    """
    await reset_async_engine()
    yield
    await reset_async_engine()


@pytest.fixture
def async_config():
    return DatabaseConfig.for_testing(url="sqlite:///:memory:")


class TestAsyncEngine:
    async def test_get_async_engine_creates_engine(self, async_config):
        engine = get_async_engine(async_config)
        assert engine is not None

    async def test_get_async_engine_is_singleton(self, async_config):
        engine1 = get_async_engine(async_config)
        engine2 = get_async_engine(async_config)
        assert engine1 is engine2

    async def test_get_async_engine_raises_without_database_url(self):
        empty_config = DatabaseConfig(url="")
        with pytest.raises(RuntimeError, match="DATABASE_URL"):
            get_async_engine(empty_config)


class TestAsyncSession:
    async def test_session_executes_query(self, async_config):
        engine = get_async_engine(async_config)
        async with get_async_session(engine) as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1

    async def test_session_commits_on_success(self, async_config):
        engine = get_async_engine(async_config)
        async with get_async_session(engine) as session:
            await session.execute(text("CREATE TABLE t (id INTEGER)"))
            await session.execute(text("INSERT INTO t (id) VALUES (1)"))

        async with get_async_session(engine) as session:
            result = await session.execute(text("SELECT COUNT(*) FROM t"))
            assert result.scalar() == 1

    async def test_session_rolls_back_on_exception(self, async_config):
        engine = get_async_engine(async_config)
        async with get_async_session(engine) as session:
            await session.execute(text("CREATE TABLE t2 (id INTEGER)"))

        with pytest.raises(ValueError):
            async with get_async_session(engine) as session:
                await session.execute(text("INSERT INTO t2 (id) VALUES (1)"))
                raise ValueError("simulated failure mid-transaction")

        async with get_async_session(engine) as session:
            result = await session.execute(text("SELECT COUNT(*) FROM t2"))
            assert result.scalar() == 0


class TestSyncAsyncIndependence:
    """Confirm the Sprint 7 addition does not disturb the Sprint 6 sync path."""

    def test_sync_get_engine_still_works(self):
        from sqlalchemy import create_engine
        from database.session import get_session, reset_engine

        reset_engine()
        eng = create_engine("sqlite:///:memory:")
        with get_session(eng) as session:
            result = session.execute(text("SELECT 1"))
            assert result.scalar() == 1
        reset_engine()
