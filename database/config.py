"""
database/config.py — DatabaseConfig: reads connection settings from environment.

Why a dedicated config class (not reading os.environ directly in session.py):
    • Mirrors the pattern established in Sprint 3–5 (SpeechProcessingConfig,
      ExtractionConfig, GenerationConfig all have from_env() class methods).
    • Keeps session.py focused on connection management, not env-var parsing.
    • Enables test code to inject a custom config without touching os.environ.

Environment variables read:
    DATABASE_URL          — SQLAlchemy connection string (required for real DB)
    DATABASE_ECHO         — Log all SQL statements (default: false)
    DATABASE_POOL_SIZE    — Connection pool size (default: 5)
    DATABASE_MAX_OVERFLOW — Extra connections beyond pool_size (default: 10)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class DatabaseConfig:
    """Connection and pool configuration for the PostgreSQL database."""

    url: str = ""
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10
    pool_pre_ping: bool = True

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Read configuration from environment variables.

        Does NOT raise if DATABASE_URL is missing — the session factory raises
        when an actual connection is attempted. This keeps imports cheap.
        """
        return cls(
            url=os.environ.get("DATABASE_URL", ""),
            echo=os.environ.get("DATABASE_ECHO", "false").lower() == "true",
            pool_size=int(os.environ.get("DATABASE_POOL_SIZE", "5")),
            max_overflow=int(os.environ.get("DATABASE_MAX_OVERFLOW", "10")),
            pool_pre_ping=True,
        )

    @classmethod
    def for_testing(cls, url: str = "sqlite:///:memory:") -> "DatabaseConfig":
        """Return a config suitable for in-memory SQLite testing.

        SQLite is used for all unit tests — no PostgreSQL required.
        The Alembic migration targets PostgreSQL; tests use
        Base.metadata.create_all() directly to stay DB-agnostic.
        """
        return cls(
            url=url,
            echo=False,
            pool_size=1,
            max_overflow=0,
            pool_pre_ping=False,
        )

    def is_configured(self) -> bool:
        """True if a non-empty DATABASE_URL is set."""
        return bool(self.url)

    def is_postgresql(self) -> bool:
        return self.url.startswith("postgresql") or self.url.startswith("postgres")

    def is_sqlite(self) -> bool:
        return self.url.startswith("sqlite")
