"""
database/ — Sprint 6 persistence layer for Construction Site AI.

Public API:
    from database import Base, get_session, DatabaseConfig
    from database.models import DailyLog, Project, Company, GenerationOutput
    from database.repositories import DailyLogRepository, ProjectRepository

Architecture:
    config.py      — DatabaseConfig: reads DATABASE_URL from environment
    base.py        — DeclarativeBase shared by all ORM models
    mixins.py      — UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, AuditUserMixin
    session.py     — engine + session factory; get_session() context manager
    models/        — SQLAlchemy 2.x ORM models (24 tables across 8 files)
    repositories/  — Clean data-access layer; business logic never touches Session directly
    seed/          — Deterministic seed scripts for reference data and sample data
    migrations/    — Alembic migrations (version-controlled schema changes)

Design philosophy:
    • 3NF throughout — no denormalization unless documented
    • UUID v4 primary keys — consistent with ConstructionDailyLog schema (ADR-002)
    • Soft deletes — records are never hard-deleted by default
    • Audit timestamps — every mutable table has created_at, updated_at, deleted_at
    • Repository pattern — session management never leaks into business logic
    • SQLite-compatible ORM models — all tests run without a PostgreSQL instance
"""

from database.base import Base
from database.config import DatabaseConfig
from database.session import get_session, get_engine

__all__ = ["Base", "DatabaseConfig", "get_session", "get_engine"]
