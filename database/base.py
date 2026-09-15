"""
database/base.py — Declarative Base for all SQLAlchemy ORM models.

Why a dedicated base.py (not inline in models/__init__.py):
    • Alembic's env.py must import Base to discover all mapped tables for
      auto-generated migrations. Having Base in its own file avoids circular
      imports when env.py imports from database.base before any model files
      have been imported.
    • All model files import from database.base. If Base were in models/,
      the first model file imported would define Base, but subsequent model
      files would need to re-import from the first — fragile ordering.
    • Mirrors the pattern used in every production SQLAlchemy codebase.

Usage:
    from database.base import Base

    class MyModel(Base):
        __tablename__ = "my_table"
        ...
"""
from __future__ import annotations

from sqlalchemy import JSON, MetaData
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase

# JSON columns render as PostgreSQL JSONB in production and plain JSON on
# SQLite (the test suite's in-memory database, which has no JSONB type).
#
# Why this exists rather than a bare `JSON`: migration 001 created every
# JSON column as JSONB (see its own docstring — "JSON columns use JSONB
# for indexability and compression"), but the models declared generic
# `JSON`, which autogenerate renders as `json`. The two disagreed, so
# `alembic check` reported perpetual drift on 22 columns — noise that
# would eventually hide a real schema change. The live database was
# always right; the models were the ones understating the type.
#
# with_variant() keeps SQLite working: a plain JSONB import would make
# every model file fail to create its table under the test engine.
JSONType = JSON().with_variant(JSONB(), "postgresql")

# Deterministic constraint names for Alembic autogenerate.
# Without this, Alembic generates names like "fk_abc123" that differ
# across databases and make migration diffs unreadable.
_NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models.

    All models inherit from this class. Alembic's env.py imports it to
    discover all mapped tables via Base.metadata.

    No columns or methods are added here — shared columns live in mixins.py
    so each mixin's purpose is explicit and composable.
    """
    metadata = MetaData(naming_convention=_NAMING_CONVENTION)
