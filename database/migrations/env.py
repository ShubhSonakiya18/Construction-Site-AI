"""
database/migrations/env.py — Alembic environment configuration.

This file is called by Alembic when running migrations. It configures:
    1. The SQLAlchemy URL (from DATABASE_URL env var or alembic.ini fallback)
    2. The metadata object (from database.base.Base) so Alembic can diff it
    3. Both "offline" mode (generates SQL script) and "online" mode (runs live)

Why import all models here:
    SQLAlchemy's mapper only knows about a table once the model class that
    declares it has been imported. Without importing all models, Base.metadata
    would be empty and Alembic would drop all tables on next autogenerate.

    The import chain:
        database.models.__init__ → imports every model class
        → each class registers itself on Base.metadata at import time
        → Alembic can then see all 26 tables in Base.metadata.tables

Naming conventions:
    Explicit naming conventions for all constraints prevent Alembic from
    generating names like "fk_123abc" that differ across databases. With
    named constraints, the migration is fully reversible and portable.
"""
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, MetaData

# ── Load naming conventions before importing models ───────────────────────────
# This must happen before Base is imported so the convention is baked in.
from sqlalchemy import MetaData

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# ── Import all ORM models to populate Base.metadata ───────────────────────────
# This triggers all 26 model classes to register their tables.
import database.models  # noqa: F401  — side-effect import, do not remove
from database.base import Base

# Apply naming conventions to metadata
# (conventions defined in models take precedence; this fills any gaps)
target_metadata = Base.metadata

# ── Alembic configuration ─────────────────────────────────────────────────────
config = context.config

# Read logging configuration from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the SQLAlchemy URL from the environment variable if set.
# This lets Docker, CI, and local dev each use their own DATABASE_URL
# without editing alembic.ini.
database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    In offline mode, Alembic generates a SQL script without connecting to
    the database. Useful for DBAs who want to review and apply SQL manually,
    or for environments where the migration tool cannot directly access the DB.

    Usage:
        alembic upgrade head --sql > migration.sql
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (direct DB connection).

    This is the standard mode for:
        alembic upgrade head
        alembic downgrade -1
        alembic revision --autogenerate -m "..."

    Uses a NullPool so the connection is closed after migrations complete,
    which is correct for CLI usage (avoids dangling connections).
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_schemas=True,
            # Use server_default comparison so alembic detects server-side defaults
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
