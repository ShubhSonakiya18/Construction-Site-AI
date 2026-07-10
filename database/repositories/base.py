"""
database/repositories/base.py — Generic CRUD repository.

Design:
    BaseRepository[T] is a generic class parameterized by the ORM model type T.
    Concrete repositories inherit it and pass their model class to super().__init__().

    Example:
        class DailyLogRepository(BaseRepository[DailyLog]):
            def __init__(self, session: Session):
                super().__init__(session, DailyLog)

    Why generic over a base class with abstract methods:
        • 80% of repository methods are identical across entities (get_by_id,
          list_all, create, update, soft_delete). Generics eliminate that boilerplate.
        • The remaining 20% are domain-specific and defined in subclasses.
        • Type checkers (mypy, pyright) correctly infer T from the class definition,
          so callers of DailyLogRepository get DailyLog-typed return values without
          any casts.

    Why NOT use the Session directly in business logic:
        • FastAPI routes are testable without a database by injecting a mock repository.
        • The session commit/rollback lifecycle is managed by get_session() context
          manager — business logic should not know about transaction boundaries.
        • A repository can be replaced with a Redis cache, an external API, or an
          in-memory store for testing without changing any business logic.

Soft delete behavior:
    list() and get_by_id() filter deleted_at IS NULL by default.
    Pass include_deleted=True to include soft-deleted records.
    hard_delete() physically removes the row — reserved for GDPR right-to-erasure.

Pagination:
    list() accepts limit/offset for consistent pagination across all entities.
    Sprint 7 FastAPI will expose these as query parameters.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, Optional, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.mixins import SoftDeleteMixin

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """Generic repository providing standard CRUD operations for any ORM model.

    Concrete repositories inherit this class and add domain-specific methods.
    The session is injected — never created inside the repository.
    """

    def __init__(self, session: Session, model: Type[T]) -> None:
        self._session = session
        self._model = model

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_by_id(self, entity_id: object, *, include_deleted: bool = False) -> Optional[T]:
        """Return a single record by primary key, or None if not found.

        Args:
            entity_id: The UUID primary key value.
            include_deleted: If True, also return soft-deleted records.
        """
        instance = self._session.get(self._model, entity_id)
        if instance is None:
            return None
        if not include_deleted and isinstance(instance, SoftDeleteMixin):
            if instance.is_deleted:
                return None
        return instance

    def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> list[T]:
        """Return a paginated list of records.

        Args:
            limit: Maximum number of records to return. Default 100.
            offset: Number of records to skip. Default 0.
            include_deleted: If True, include soft-deleted records.
        """
        stmt = select(self._model)
        if not include_deleted and issubclass(self._model, SoftDeleteMixin):
            stmt = stmt.where(self._model.deleted_at.is_(None))  # type: ignore[attr-defined]
        stmt = stmt.limit(limit).offset(offset)
        return list(self._session.execute(stmt).scalars().all())

    def count(self, *, include_deleted: bool = False) -> int:
        """Return the total count of records (respects soft delete filter)."""
        from sqlalchemy import func as sqla_func
        stmt = select(sqla_func.count()).select_from(self._model)
        if not include_deleted and issubclass(self._model, SoftDeleteMixin):
            stmt = stmt.where(self._model.deleted_at.is_(None))  # type: ignore[attr-defined]
        result = self._session.execute(stmt).scalar_one()
        return result

    def exists(self, entity_id: object) -> bool:
        """Return True if a non-deleted record with this ID exists."""
        return self.get_by_id(entity_id) is not None

    # ── Write ─────────────────────────────────────────────────────────────────

    def create(self, instance: T) -> T:
        """Persist a new record. The instance must not yet be in the session.

        Returns the same instance (now attached to the session with server-set
        values like created_at populated after flush).
        """
        self._session.add(instance)
        self._session.flush()
        return instance

    def update(self, instance: T) -> T:
        """Persist changes to an existing record.

        The instance must already be attached to the session (retrieved via
        get_by_id or list). Call session.flush() to write to DB without commit.
        """
        self._session.flush()
        return instance

    def soft_delete(self, instance: T) -> T:
        """Mark a record as soft-deleted by setting deleted_at to now.

        Raises:
            TypeError: if the model does not use SoftDeleteMixin.
        """
        if not isinstance(instance, SoftDeleteMixin):
            raise TypeError(
                f"{self._model.__name__} does not support soft delete "
                "(missing SoftDeleteMixin). Use hard_delete() instead."
            )
        instance.deleted_at = datetime.now(timezone.utc)
        self._session.flush()
        return instance

    def restore(self, instance: T) -> T:
        """Un-delete a soft-deleted record by clearing deleted_at.

        Raises:
            TypeError: if the model does not use SoftDeleteMixin.
        """
        if not isinstance(instance, SoftDeleteMixin):
            raise TypeError(
                f"{self._model.__name__} does not support soft delete."
            )
        instance.deleted_at = None  # type: ignore[assignment]
        self._session.flush()
        return instance

    def hard_delete(self, instance: T) -> None:
        """Physically remove a record from the database.

        Use for GDPR right-to-erasure only. For normal deletions, use soft_delete().
        """
        self._session.delete(instance)
        self._session.flush()
