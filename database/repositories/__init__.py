"""
database/repositories/ — Clean data-access layer.

Business logic (AI services, CLI commands, FastAPI endpoints) never touches
SQLAlchemy Session objects directly. All database operations go through a
repository class.

Pattern:
    with get_session() as session:
        repo = DailyLogRepository(session)
        log = repo.get_by_id(log_id)
        log.review_status = "approved"
        repo.update(log)
    # session auto-commits and closes

Repository classes in this package:
    BaseRepository     — generic CRUD (get, list, create, update, soft_delete, hard_delete)
    CompanyRepository  — Company + User management
    ProjectRepository  — Project + Site + ProjectWorker management
    WorkerRepository   — Worker lookup and management
    AudioRepository    — AudioFile + SpeechTranscript operations
    DailyLogRepository — DailyLog + all log child tables
    GenerationRepository — GenerationOutput + AuditLog
"""

from database.repositories.base import BaseRepository
from database.repositories.company import CompanyRepository, UserRepository
from database.repositories.project import ProjectRepository, SiteRepository
from database.repositories.worker import WorkerRepository
from database.repositories.audio import AudioRepository
from database.repositories.daily_log import DailyLogRepository
from database.repositories.generation import GenerationRepository, AuditLogRepository

__all__ = [
    "BaseRepository",
    "CompanyRepository",
    "UserRepository",
    "ProjectRepository",
    "SiteRepository",
    "WorkerRepository",
    "AudioRepository",
    "DailyLogRepository",
    "GenerationRepository",
    "AuditLogRepository",
]
