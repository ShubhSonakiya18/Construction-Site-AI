"""
database/repositories/worker.py — Worker repository.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models.worker import Worker
from database.repositories.base import BaseRepository


class WorkerRepository(BaseRepository[Worker]):
    """Repository for Worker (people who appear on construction sites)."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Worker)

    def list_by_company(
        self,
        company_id: UUID,
        *,
        trade_id: Optional[UUID] = None,
        role: Optional[str] = None,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Worker]:
        """List workers for a company with optional trade and role filters."""
        stmt = (
            select(Worker)
            .where(Worker.company_id == company_id)
            .where(Worker.deleted_at.is_(None))
        )
        if active_only:
            stmt = stmt.where(Worker.is_active.is_(True))
        if trade_id is not None:
            stmt = stmt.where(Worker.trade_id == trade_id)
        if role is not None:
            stmt = stmt.where(Worker.role == role)
        stmt = stmt.order_by(Worker.last_name, Worker.first_name).limit(limit).offset(offset)
        return list(self._session.execute(stmt).scalars().all())

    def get_foremen(self, company_id: UUID) -> list[Worker]:
        """Return all active foremen for a company."""
        return self.list_by_company(company_id, role="foreman")

    def find_by_name(self, company_id: UUID, name: str) -> list[Worker]:
        """Search workers by name (case-insensitive substring).

        Used by the repository layer to link voice-extracted foreman_name
        strings to Worker records when the sprint 4 ExtractionPipeline
        extracts a foreman_name from a transcript.
        """
        from sqlalchemy import or_, func
        search = f"%{name.lower()}%"
        stmt = (
            select(Worker)
            .where(Worker.company_id == company_id)
            .where(Worker.deleted_at.is_(None))
            .where(Worker.is_active.is_(True))
            .where(
                or_(
                    func.lower(Worker.first_name).like(search),
                    func.lower(Worker.last_name).like(search),
                )
            )
        )
        return list(self._session.execute(stmt).scalars().all())

    def get_by_user_id(self, user_id: UUID) -> Optional[Worker]:
        """Find the Worker record linked to a User account (if any)."""
        stmt = (
            select(Worker)
            .where(Worker.user_id == user_id)
            .where(Worker.deleted_at.is_(None))
        )
        return self._session.execute(stmt).scalar_one_or_none()
