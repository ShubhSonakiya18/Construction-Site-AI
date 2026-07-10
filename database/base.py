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

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models.

    All models inherit from this class. Alembic's env.py imports it to
    discover all mapped tables via Base.metadata.

    No columns or methods are added here — shared columns live in mixins.py
    so each mixin's purpose is explicit and composable.
    """
    pass
