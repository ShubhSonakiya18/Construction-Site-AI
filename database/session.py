"""
database/session.py — Engine creation and session factory.

Why a context-manager session (not a global session):
    Global sessions are one of the most common SQLAlchemy anti-patterns.
    A global session leaks state across requests (in a web API), causes
    subtle bugs with detached instances, and makes testing painful.

    The pattern here:
        with get_session() as session:
            repo = DailyLogRepository(session)
            log = repo.get_by_id(log_id)

    • The session is created fresh for each unit of work.
    • Commit is called automatically on successful exit.
    • Rollback is called automatically on exception.
    • The session is always closed on exit (returns connection to pool).

Why separate get_engine() and get_session():
    get_engine() creates the connection pool (expensive, once per process).
    get_session() opens a logical session from the pool (cheap, per request).
    Tests override get_engine() by calling create_engine("sqlite:///:memory:")
    directly — they never call get_engine() from this module.

Thread safety:
    SQLAlchemy's engine is thread-safe and shared. Sessions are NOT thread-safe
    and must not be shared across threads. The context manager pattern enforces
    this by creating a new session per call.

Sync vs. async — when to use which (Sprint 7):
    get_session() (sync, this module, unchanged since Sprint 6):
        • All Sprint 1-6 CLI tools: transcribe.py, extract.py, generate.py,
          verify_sprint6.py, seed scripts, pytest test suite.
        • Any code that is not an async FastAPI route handler.
        • Driver: psycopg2 (blocking).

    get_async_session() (async, added in Sprint 7, below):
        • Direct SQLAlchemy Core / raw-SQL usage from async code — e.g. a
          lightweight `SELECT 1` health check, or hand-written async queries
          that do not go through the repository layer.
        • NOT for use with database/repositories/*.py. BaseRepository and
          every repository built on it call session.execute()/.get()/.flush()/
          .delete() synchronously (no `await`). Handing an AsyncSession to a
          repository does not raise — it silently returns unawaited coroutine
          objects instead of results. The repository layer stays sync-only by
          design (see docs/BACKEND_ARCHITECTURE.md for the full rationale).
        • app/ FastAPI routes that need repository access use the sync
          get_session() instead — FastAPI runs sync dependency functions in
          a worker threadpool automatically, so this does not block the
          event loop despite being "sync" code.

    Both read the same DATABASE_URL from DatabaseConfig — the async path
    rewrites the scheme (postgresql:// -> postgresql+asyncpg://) internally,
    so .env needs only one DATABASE_URL for both code paths.

    The two engines, pools, and session factories are entirely independent
    singletons (separate module-level globals). Neither code path touches
    the other's state. Existing sync callers are unaffected by this addition.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator, Optional

from sqlalchemy import create_engine, Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from database.config import DatabaseConfig

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None
_SessionFactory: Optional[sessionmaker] = None

_async_engine: Optional[AsyncEngine] = None
_AsyncSessionFactory: Optional[async_sessionmaker] = None


def get_engine(config: Optional[DatabaseConfig] = None) -> Engine:
    """Return the process-singleton SQLAlchemy engine.

    Creates the engine on first call; subsequent calls return the cached instance.
    Pass a custom `config` to override (primarily for testing).

    Raises:
        RuntimeError: if no DATABASE_URL is configured.
    """
    global _engine
    if _engine is None:
        cfg = config or DatabaseConfig.from_env()
        if not cfg.is_configured():
            raise RuntimeError(
                "DATABASE_URL environment variable is not set. "
                "Copy .env.example to .env and set DATABASE_URL."
            )
        kwargs: dict = {
            "echo": cfg.echo,
            "pool_pre_ping": cfg.pool_pre_ping,
        }
        # SQLite does not support pool_size / max_overflow
        if not cfg.is_sqlite():
            kwargs["pool_size"] = cfg.pool_size
            kwargs["max_overflow"] = cfg.max_overflow

        _engine = create_engine(cfg.url, **kwargs)
        logger.info(
            "Database engine created: %s (pool_size=%s)",
            cfg.url.split("@")[-1] if "@" in cfg.url else cfg.url,
            cfg.pool_size,
        )
    return _engine


def _get_session_factory(engine: Optional[Engine] = None) -> sessionmaker:
    """Return the session factory (cached singleton)."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(
            bind=engine or get_engine(),
            expire_on_commit=False,
        )
    return _SessionFactory


@contextmanager
def get_session(engine: Optional[Engine] = None) -> Generator[Session, None, None]:
    """Context manager that yields a database session with automatic lifecycle management.

    Usage:
        with get_session() as session:
            repo = DailyLogRepository(session)
            log = repo.create(DailyLog(...))
        # session is committed and closed here

    On exception, the session is rolled back before closing.
    The `engine` parameter is only used in tests to inject a SQLite engine.
    """
    factory = _get_session_factory(engine)
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    """Dispose the sync engine and reset the singleton. Used in tests only.

    Does not touch the async engine — call reset_async_engine() separately
    if a test also needs to reset async state. Kept separate because most
    Sprint 1-6 tests never create an async engine at all.
    """
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None


# ═══════════════════════════════════════════════════════════════════════════
# Async engine and session (Sprint 7 — for FastAPI route handlers)
# ═══════════════════════════════════════════════════════════════════════════


def _to_async_url(url: str) -> str:
    """Rewrite a sync SQLAlchemy URL to its async-driver equivalent.

    postgresql://...          -> postgresql+asyncpg://...
    postgresql+psycopg2://... -> postgresql+asyncpg://...
    sqlite://...               -> sqlite+aiosqlite://...

    Lets both sync and async code read the exact same DATABASE_URL from
    .env — no second env var to keep in sync.
    """
    if url.startswith("postgresql+asyncpg://") or url.startswith("sqlite+aiosqlite://"):
        return url  # already async
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1).replace(
            "postgres://", "postgresql+asyncpg://", 1
        )
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url


def get_async_engine(config: Optional[DatabaseConfig] = None) -> AsyncEngine:
    """Return the process-singleton async SQLAlchemy engine.

    Mirrors get_engine() exactly, but builds an AsyncEngine bound to
    asyncpg (or aiosqlite for sqlite:// URLs in tests). Creates the engine
    on first call; subsequent calls return the cached instance.

    Raises:
        RuntimeError: if no DATABASE_URL is configured.
    """
    global _async_engine
    if _async_engine is None:
        cfg = config or DatabaseConfig.from_env()
        if not cfg.is_configured():
            raise RuntimeError(
                "DATABASE_URL environment variable is not set. "
                "Copy .env.example to .env and set DATABASE_URL."
            )
        async_url = _to_async_url(cfg.url)
        kwargs: dict = {
            "echo": cfg.echo,
            "pool_pre_ping": cfg.pool_pre_ping,
        }
        # SQLite does not support pool_size / max_overflow (same constraint
        # as the sync engine above).
        if not cfg.is_sqlite():
            kwargs["pool_size"] = cfg.pool_size
            kwargs["max_overflow"] = cfg.max_overflow

        _async_engine = create_async_engine(async_url, **kwargs)
        logger.info(
            "Async database engine created: %s (pool_size=%s)",
            async_url.split("@")[-1] if "@" in async_url else async_url,
            cfg.pool_size,
        )
    return _async_engine


def _get_async_session_factory(
    engine: Optional[AsyncEngine] = None,
) -> async_sessionmaker:
    """Return the async session factory (cached singleton)."""
    global _AsyncSessionFactory
    if _AsyncSessionFactory is None:
        _AsyncSessionFactory = async_sessionmaker(
            bind=engine or get_async_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _AsyncSessionFactory


@asynccontextmanager
async def get_async_session(
    engine: Optional[AsyncEngine] = None,
) -> AsyncGenerator[AsyncSession, None]:
    """Async context manager yielding a database session for FastAPI routes.

    Usage:
        async with get_async_session() as session:
            repo = DailyLogRepository(session)  # repos work with AsyncSession too —
            log = await session.get(DailyLog, log_id)  # but await the actual I/O calls

    Same lifecycle guarantees as the sync get_session(): commit on success,
    rollback on exception, always closed on exit. The `engine` parameter is
    only used in tests to inject an aiosqlite in-memory engine.
    """
    factory = _get_async_session_factory(engine)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def reset_async_engine() -> None:
    """Dispose the async engine and reset the singleton. Used in tests only."""
    global _async_engine, _AsyncSessionFactory
    if _async_engine is not None:
        await _async_engine.dispose()
    _async_engine = None
    _AsyncSessionFactory = None
