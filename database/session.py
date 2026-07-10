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
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import Session, sessionmaker

from database.config import DatabaseConfig

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None
_SessionFactory: Optional[sessionmaker] = None


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
    """Dispose the engine and reset the singleton. Used in tests only."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None
