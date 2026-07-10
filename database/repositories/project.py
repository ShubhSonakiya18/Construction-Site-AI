"""
database/repositories/project.py — Project, Site, and ProjectWorker repositories.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models.project import Project, ProjectWorker, Site
from database.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    """Repository for Project (primary grouping for daily logs)."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Project)

    def list_by_company(
        self,
        company_id: UUID,
        *,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Project]:
        """List active projects for a company, optionally filtered by status."""
        stmt = (
            select(Project)
            .where(Project.company_id == company_id)
            .where(Project.deleted_at.is_(None))
        )
        if status is not None:
            stmt = stmt.where(Project.status == status)
        stmt = stmt.order_by(Project.name).limit(limit).offset(offset)
        return list(self._session.execute(stmt).scalars().all())

    def list_active(self, company_id: UUID) -> list[Project]:
        """Return all projects in 'active' status for a company."""
        return self.list_by_company(company_id, status="active", limit=1000)

    def get_with_sites(self, project_id: UUID) -> Optional[Project]:
        """Return a project with its sites eagerly loaded."""
        from sqlalchemy.orm import selectinload
        stmt = (
            select(Project)
            .where(Project.id == project_id)
            .where(Project.deleted_at.is_(None))
            .options(selectinload(Project.sites))
        )
        return self._session.execute(stmt).scalar_one_or_none()


class SiteRepository(BaseRepository[Site]):
    """Repository for Site (physical construction site locations)."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, Site)

    def list_by_project(self, project_id: UUID) -> list[Site]:
        """Return all sites for a project."""
        stmt = (
            select(Site)
            .where(Site.project_id == project_id)
            .order_by(Site.is_primary.desc(), Site.address)
        )
        return list(self._session.execute(stmt).scalars().all())

    def get_primary(self, project_id: UUID) -> Optional[Site]:
        """Return the primary site for a project."""
        stmt = (
            select(Site)
            .where(Site.project_id == project_id)
            .where(Site.is_primary.is_(True))
        )
        return self._session.execute(stmt).scalar_one_or_none()


class ProjectWorkerRepository(BaseRepository[ProjectWorker]):
    """Repository for ProjectWorker (worker-project assignment junction)."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, ProjectWorker)

    def list_active_for_project(self, project_id: UUID) -> list[ProjectWorker]:
        """Return all active worker assignments for a project."""
        stmt = (
            select(ProjectWorker)
            .where(ProjectWorker.project_id == project_id)
            .where(ProjectWorker.is_active.is_(True))
        )
        return list(self._session.execute(stmt).scalars().all())

    def get_assignment(
        self, project_id: UUID, worker_id: UUID
    ) -> Optional[ProjectWorker]:
        """Return the assignment record for a specific worker on a project."""
        stmt = (
            select(ProjectWorker)
            .where(ProjectWorker.project_id == project_id)
            .where(ProjectWorker.worker_id == worker_id)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def is_assigned(self, project_id: UUID, worker_id: UUID) -> bool:
        """Return True if this worker has an active assignment on this project."""
        assignment = self.get_assignment(project_id, worker_id)
        return assignment is not None and assignment.is_active
