"""
database/repositories/company.py — Company and User repositories.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models.company import Company, User
from database.repositories.base import BaseRepository


class CompanyRepository(BaseRepository[Company]):
    """Repository for Company (multi-tenancy root entity)."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Company)

    def get_by_slug(self, slug: str) -> Optional[Company]:
        """Find an active company by its URL slug."""
        stmt = (
            select(Company)
            .where(Company.slug == slug)
            .where(Company.deleted_at.is_(None))
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_by_email(self, email: str) -> Optional[Company]:
        """Find an active company by contact email."""
        stmt = (
            select(Company)
            .where(Company.contact_email == email)
            .where(Company.deleted_at.is_(None))
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def list_active(self, *, limit: int = 100, offset: int = 0) -> list[Company]:
        """List all active (non-deleted, is_active=True) companies."""
        stmt = (
            select(Company)
            .where(Company.deleted_at.is_(None))
            .where(Company.is_active.is_(True))
            .order_by(Company.name)
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.execute(stmt).scalars().all())

    def slug_exists(self, slug: str) -> bool:
        """Return True if a company with this slug already exists."""
        from sqlalchemy import func
        stmt = (
            select(func.count())
            .select_from(Company)
            .where(Company.slug == slug)
        )
        return self._session.execute(stmt).scalar_one() > 0


class UserRepository(BaseRepository[User]):
    """Repository for User (application login accounts)."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, User)

    def get_by_email(self, email: str) -> Optional[User]:
        """Find a user by email address (unique across all companies)."""
        stmt = (
            select(User)
            .where(User.email == email)
            .where(User.deleted_at.is_(None))
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def list_by_company(
        self,
        company_id: UUID,
        *,
        role: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[User]:
        """List active users belonging to a company, optionally filtered by role."""
        stmt = (
            select(User)
            .where(User.company_id == company_id)
            .where(User.deleted_at.is_(None))
        )
        if role is not None:
            stmt = stmt.where(User.role == role)
        stmt = stmt.order_by(User.last_name, User.first_name).limit(limit).offset(offset)
        return list(self._session.execute(stmt).scalars().all())

    def email_exists(self, email: str) -> bool:
        """Return True if this email is already registered."""
        from sqlalchemy import func
        stmt = (
            select(func.count())
            .select_from(User)
            .where(User.email == email)
        )
        return self._session.execute(stmt).scalar_one() > 0
