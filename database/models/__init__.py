"""
database/models/__init__.py — Import all ORM models in one place.

WHY THIS FILE EXISTS:
    Alembic's env.py does:
        from database.models import *   (or imports Base and all models)
    This triggers SQLAlchemy's mapper to register all tables under Base.metadata.
    Without this file, Alembic would see an empty metadata and generate empty
    migrations.

    Additionally, FastAPI's lifespan and the seed scripts import from here so
    they don't need to know which model lives in which file.

IMPORT ORDER:
    SQLAlchemy resolves ForeignKey("tablename.column") lazily (at mapper
    configuration time), so import ORDER doesn't technically matter for FK
    resolution. However, we import in a logical dependency order for clarity:
        1. Reference tables (no FKs to business tables)
        2. Company, User (top of multi-tenancy hierarchy)
        3. UserSession, PasswordResetToken (reference User) — Sprint 8
        4. Worker (references Company + User)
        5. Project, Site, ProjectWorker (references Company + Worker)
        6. Audio, Transcript (references Project + User)
        7. DailyLog (references Project + Site + AudioFile + Worker)
        8. Log child tables (all reference DailyLog)
        9. GenerationOutput (references DailyLog)
        10. AuditLog (no FKs — immutable event log)

TOTAL: 28 tables
    Reference:  Trade, ConstructionStage, MaterialCategory, PPEType (4)
    Company:    Company, User (2)
    Auth:       UserSession, PasswordResetToken (2) — Sprint 8
    Worker:     Worker (1)
    Project:    Project, Site, ProjectWorker (3)
    Audio:      AudioFile, SpeechTranscript (2)
    DailyLog:   DailyLog (1)
    Log items:  LogTradeOnSite, LogWorkItem, LogWorkInProgress,
                LogMaterialUsed, LogMaterialDelivered, LogMaterialRequired,
                LogEquipment, LogSafetyIncident, LogHazard, LogDelay,
                LogInspection (11)
    Generation: GenerationOutput (1)
    Audit:      AuditLog (1)
"""

# ── Reference tables ──────────────────────────────────────────────────────────
from database.models.reference import (
    ConstructionStage,
    MaterialCategory,
    PPEType,
    Trade,
)

# ── Company and users ─────────────────────────────────────────────────────────
from database.models.company import Company, User

# ── Auth sessions + password reset (Sprint 8) ─────────────────────────────────
from database.models.auth import UserSession
from database.models.password_reset import PasswordResetToken

# ── Workers ───────────────────────────────────────────────────────────────────
from database.models.worker import Worker

# ── Projects ──────────────────────────────────────────────────────────────────
from database.models.project import Project, ProjectWorker, Site

# ── Audio pipeline ────────────────────────────────────────────────────────────
from database.models.audio import AudioFile, SpeechTranscript

# ── Daily logs (core) ─────────────────────────────────────────────────────────
from database.models.daily_log import DailyLog

# ── Log child tables ──────────────────────────────────────────────────────────
from database.models.log_items import (
    LogDelay,
    LogEquipment,
    LogHazard,
    LogInspection,
    LogMaterialDelivered,
    LogMaterialRequired,
    LogMaterialUsed,
    LogSafetyIncident,
    LogTradeOnSite,
    LogWorkInProgress,
    LogWorkItem,
)

# ── AI Generation outputs ─────────────────────────────────────────────────────
from database.models.generation import AuditLog, GenerationOutput

__all__ = [
    # Reference
    "Trade",
    "ConstructionStage",
    "MaterialCategory",
    "PPEType",
    # Company
    "Company",
    "User",
    # Auth sessions + password reset (Sprint 8)
    "UserSession",
    "PasswordResetToken",
    # Worker
    "Worker",
    # Project
    "Project",
    "Site",
    "ProjectWorker",
    # Audio
    "AudioFile",
    "SpeechTranscript",
    # Daily log
    "DailyLog",
    # Log children
    "LogTradeOnSite",
    "LogWorkItem",
    "LogWorkInProgress",
    "LogMaterialUsed",
    "LogMaterialDelivered",
    "LogMaterialRequired",
    "LogEquipment",
    "LogSafetyIncident",
    "LogHazard",
    "LogDelay",
    "LogInspection",
    # Generation
    "GenerationOutput",
    "AuditLog",
]
