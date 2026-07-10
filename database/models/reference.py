"""
database/models/reference.py — Immutable reference / lookup tables.

These tables hold the domain vocabulary of residential construction.
They are populated once by the seed scripts and read-only at runtime.

Why separate reference tables (not Python Enums in columns):
    • Python Enums bake the valid values into the schema migration. Adding a
      new trade type requires a database migration (ALTER TYPE ... ADD VALUE).
    • Reference tables let new values be added with a simple INSERT — no migration.
    • Reference rows carry extra metadata (display_name, is_licensed, description)
      that a column constraint cannot express.
    • Sprint 7 API can expose these tables via /api/v1/reference/trades,
      enabling the frontend dropdown to list valid values dynamically.
    • The JSON schema still enforces enum values for AI extraction — the DB
      reference tables are the canonical list that the schema enum was derived from.

Tables in this file:
    trades              — 24 construction trade types (electrician, plumber, etc.)
    construction_stages — 22 construction stage codes (matches current_stage enum)
    material_categories — 16 material category codes
    ppe_types           — 16 PPE item types
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base
from database.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Trade(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A construction trade type.

    Matches the `trade` enum values in ConstructionDailyLog.workforce.trades_on_site
    and log_work_items.trade_name.

    Seeded from knowledge/construction_ontology.json.
    """

    __tablename__ = "trades"

    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        doc="Machine-readable code matching the JSON schema enum. e.g. 'electrician'",
    )
    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Human-readable name. e.g. 'Electrician'",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    is_licensed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="True if this trade legally requires a state/local license.",
    )
    typical_crew_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        doc="Typical crew size for daily log workforce validation.",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_trades_code", "code"),
    )

    def __repr__(self) -> str:
        return f"<Trade code={self.code!r}>"


class ConstructionStage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A residential construction stage.

    Matches the 22 values in the `current_stage` enum of ConstructionDailyLog.
    Sequence order defines the typical progression through a project — the
    dependency graph in knowledge/dependency_graph.json is the authoritative source.

    Seeded from knowledge/construction_stages.json.
    """

    __tablename__ = "construction_stages"

    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        doc="Machine-readable stage code. e.g. 'foundation', 'framing'",
    )
    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    sequence_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Typical ordering within a project. Not enforced (parallel stages exist). "
            "Used for UI display ordering.",
    )
    typical_duration_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_construction_stages_code", "code"),
        Index("ix_construction_stages_sequence", "sequence_order"),
    )

    def __repr__(self) -> str:
        return f"<ConstructionStage code={self.code!r} order={self.sequence_order}>"


class MaterialCategory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A material category used in daily log material tracking.

    Matches the `category` enum in ConstructionDailyLog.materials.used_today.
    Seeded from the JSON schema enum values.
    """

    __tablename__ = "material_categories"

    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        doc="Machine-readable code. e.g. 'concrete', 'lumber', 'electrical'",
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_material_categories_code", "code"),
    )

    def __repr__(self) -> str:
        return f"<MaterialCategory code={self.code!r}>"


class PPEType(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Personal Protective Equipment type required on construction sites.

    Matches the PPE item codes in ConstructionDailyLog.safety.ppe_required_today.
    Used by the Safety Toolbox Talk AI service (Sprint 5) for context.
    Seeded from knowledge/construction_ontology.json.
    """

    __tablename__ = "ppe_types"

    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        doc="Machine-readable PPE code. e.g. 'hard_hat', 'fall_protection_harness'",
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    osha_reference: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        doc="OSHA standard that mandates this PPE. e.g. '29 CFR 1926.100'",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_ppe_types_code", "code"),
    )

    def __repr__(self) -> str:
        return f"<PPEType code={self.code!r}>"
