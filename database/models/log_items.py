"""
database/models/log_items.py — Normalized child tables of DailyLog.

Why normalize these arrays instead of storing them as JSON on DailyLog:

    The fundamental question for each array is:
    "Will we ever need to query an individual element independently?"

    If yes → normalize (relational table).
    If no  → JSON column on DailyLog.

    Normalized here (independent query value):
        LogTradeOnSite      — "Show me all framing days across Project X this month"
        LogWorkItem         — "Find all work items in the master bathroom"
        LogWorkInProgress   — "What WIP tasks are blocking framing completion?"
        LogMaterialUsed     — "Total concrete used across Project X"
        LogMaterialDelivered— "Find all partial deliveries from supplier Y"
        LogMaterialRequired — "All critical materials needed across active projects"
        LogEquipment        — "How many hours did the boom lift operate in Q3?"
        LogSafetyIncident   — "All OSHA-recordable incidents this year" (critical query)
        LogHazard           — "High-severity hazards still unresolved"
        LogDelay            — "Total days lost to material shortage delays in Q2"
        LogInspection       — "All failed inspections with uncorrected items"

    Kept as JSON on DailyLog:
        late_arrivals / absences / visitors — attendance is analyzed at the
        workforce summary level (total_workers_present), not per-person.
        tomorrow_plan / client_communication / weather / financials — always
        consumed as a complete object by AI generators; no sub-field queries.

Primary key strategy:
    All child tables use UUIDPrimaryKeyMixin for a stable, referenceable PK.
    This allows Sprint 7 API to expose individual work items at
    GET /logs/{log_id}/work_items/{item_id} without client-side reconstruction.

Cascade delete:
    All FK references to daily_logs use ondelete="CASCADE".
    The relationship on DailyLog also specifies cascade="all, delete-orphan".
    This means: when a DailyLog is hard-deleted, all its children go with it.
    When a DailyLog is SOFT-deleted, children remain (for audit purposes).
    The repository must decide whether to cascade soft-deletes to children.
"""
from __future__ import annotations

import uuid
from datetime import date as date_type
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from database.models.daily_log import DailyLog


# ── Workforce ─────────────────────────────────────────────────────────────────

class LogTradeOnSite(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One trade group present on site for a specific daily log.

    Maps to ConstructionDailyLog.workforce.trades_on_site[].
    Normalized to support queries like:
        "Total electrician man-hours across Project X in Q3"
        "Which projects had more than 5 HVAC technicians on site?"
    """

    __tablename__ = "log_trades_on_site"

    daily_log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_logs.id", ondelete="CASCADE"),
        nullable=False,
    )
    trade: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Trade code matching the workforce.trades_on_site[].trade enum.",
    )
    workers_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    foreman_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    subcontractor_company: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        doc="Subcontractor company name if these workers are not GC employees.",
    )
    hours_worked: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 2), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    daily_log: Mapped["DailyLog"] = relationship(
        "DailyLog", back_populates="trades_on_site"
    )

    __table_args__ = (
        Index("ix_log_trades_daily_log_id", "daily_log_id"),
        Index("ix_log_trades_trade", "trade"),
    )

    def __repr__(self) -> str:
        return f"<LogTradeOnSite trade={self.trade!r} count={self.workers_count}>"


# ── Work Completed ────────────────────────────────────────────────────────────

class LogWorkItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single completed task entry from a daily log.

    Maps to ConstructionDailyLog.work_completed[].
    Normalized to support:
        "Show all work items completed in the master bathroom"
        "What framing work occurred in the last 7 days on Project X?"
    """

    __tablename__ = "log_work_items"

    daily_log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_logs.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Clear description of work accomplished. e.g., 'Framed all exterior "
            "walls on second floor north and east sides'",
    )
    trade: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Which trade performed this work.",
    )
    location_on_site: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        doc="Where on the building. e.g., 'Second floor', 'Master bathroom'",
    )
    quantity_completed: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 3), nullable=True
    )
    unit_of_measure: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="e.g., 'sq_feet', 'linear_feet', 'cubic_yards', 'each'",
    )
    task_completion_percent: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    linked_schedule_task_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="Reference to project schedule task. Used by Sprint 11 Scheduling module.",
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    daily_log: Mapped["DailyLog"] = relationship(
        "DailyLog", back_populates="work_items"
    )

    __table_args__ = (
        Index("ix_log_work_items_daily_log_id", "daily_log_id"),
        Index("ix_log_work_items_trade", "trade"),
    )

    def __repr__(self) -> str:
        return f"<LogWorkItem trade={self.trade!r} desc={self.task_description[:40]!r}>"


class LogWorkInProgress(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Work underway but not yet complete — carryover tasks to tomorrow.

    Maps to ConstructionDailyLog.work_in_progress[].
    Normalized to support:
        "Show all incomplete tasks for Project X sorted by expected completion"
        "Which WIP tasks have blocking issues right now?"
    """

    __tablename__ = "log_work_in_progress"

    daily_log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_logs.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_description: Mapped[str] = mapped_column(Text, nullable=False)
    trade: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    location_on_site: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    current_completion_percent: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    expected_completion_date: Mapped[Optional[date_type]] = mapped_column(
        Date, nullable=True
    )
    blocking_issues: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="What is preventing completion of this task.",
    )

    daily_log: Mapped["DailyLog"] = relationship(
        "DailyLog", back_populates="work_in_progress"
    )

    __table_args__ = (
        Index("ix_log_wip_daily_log_id", "daily_log_id"),
    )

    def __repr__(self) -> str:
        return f"<LogWorkInProgress desc={self.task_description[:40]!r}>"


# ── Materials ─────────────────────────────────────────────────────────────────

class LogMaterialUsed(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A material consumed during today's work.

    Maps to ConstructionDailyLog.materials.used_today[].
    Normalized to support:
        "Total concrete used across all projects in Q2"
        "Material waste analysis by category"
        "Cost of lumber across Project X to date"
    """

    __tablename__ = "log_materials_used"

    daily_log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_logs.id", ondelete="CASCADE"),
        nullable=False,
    )
    material_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Standard material name as used in procurement. "
            "e.g., 'Ready-mix concrete 4000 PSI'",
    )
    category: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="Material category code matching MaterialCategory.code.",
    )
    quantity_used: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    unit: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="e.g., 'cubic_yards', 'sheets', 'gallons'",
    )
    waste_quantity: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 3), nullable=True
    )
    unit_cost_usd: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    supplier: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    daily_log: Mapped["DailyLog"] = relationship(
        "DailyLog", back_populates="materials_used"
    )

    __table_args__ = (
        Index("ix_log_materials_used_daily_log_id", "daily_log_id"),
        Index("ix_log_materials_used_category", "category"),
    )

    def __repr__(self) -> str:
        return f"<LogMaterialUsed {self.material_name!r} qty={self.quantity_used} {self.unit}>"


class LogMaterialDelivered(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A material delivery that arrived on site today.

    Maps to ConstructionDailyLog.materials.delivered_today[].
    Normalized to support:
        "All partial or damaged deliveries from Supplier Y"
        "Delivery tracking for concrete on Project X"
        "Open purchase orders: did delivery match PO?"
    """

    __tablename__ = "log_materials_delivered"

    daily_log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_logs.id", ondelete="CASCADE"),
        nullable=False,
    )
    material_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity_delivered: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    supplier: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    delivery_condition: Mapped[Optional[str]] = mapped_column(
        String(30),
        nullable=True,
        doc="good | damaged | partial_delivery | rejected",
    )
    purchase_order_number: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    daily_log: Mapped["DailyLog"] = relationship(
        "DailyLog", back_populates="materials_delivered"
    )

    __table_args__ = (
        Index("ix_log_materials_delivered_daily_log_id", "daily_log_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<LogMaterialDelivered {self.material_name!r} "
            f"qty={self.quantity_delivered} condition={self.delivery_condition!r}>"
        )


class LogMaterialRequired(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A material that needs to be available for tomorrow's work.

    Maps to ConstructionDailyLog.materials.required_for_tomorrow[].
    Normalized to support:
        "All critical materials needed across all active projects for tomorrow"
        "Sprint 12 Inventory: which materials are consistently needed most?"
    This is the primary data source for the MaterialReminderService (Sprint 5).
    """

    __tablename__ = "log_materials_required"

    daily_log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_logs.id", ondelete="CASCADE"),
        nullable=False,
    )
    material_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity_needed: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    urgency: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="medium",
        doc="low | medium | high | critical. "
            "critical = work stops tomorrow without this material.",
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    daily_log: Mapped["DailyLog"] = relationship(
        "DailyLog", back_populates="materials_required"
    )

    __table_args__ = (
        Index("ix_log_materials_required_daily_log_id", "daily_log_id"),
        Index("ix_log_materials_required_urgency", "urgency"),
    )

    def __repr__(self) -> str:
        return (
            f"<LogMaterialRequired {self.material_name!r} "
            f"qty={self.quantity_needed} urgency={self.urgency!r}>"
        )


# ── Equipment ─────────────────────────────────────────────────────────────────

class LogEquipment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Equipment or machinery used on site today.

    Maps to ConstructionDailyLog.equipment[].
    Normalized to support:
        "Total boom lift hours across all projects in Q3 (rental cost analysis)"
        "Equipment condition history: which equipment is frequently broken?"
    """

    __tablename__ = "log_equipment"

    daily_log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_logs.id", ondelete="CASCADE"),
        nullable=False,
    )
    equipment_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="e.g., 'Caterpillar 320 Excavator', 'JLG 40ft Boom Lift'",
    )
    equipment_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="Category code: excavator | bulldozer | crane | forklift | "
            "concrete_mixer | concrete_pump | generator | boom_lift | other",
    )
    is_rented: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    hours_used: Mapped[Optional[float]] = mapped_column(Numeric(6, 2), nullable=True)
    operator: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        doc="Name or ID of the certified operator.",
    )
    equipment_condition: Mapped[Optional[str]] = mapped_column(
        String(30),
        nullable=True,
        doc="excellent | good | fair | needs_maintenance | broken_down",
    )
    maintenance_issues: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fuel_consumed_liters: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 2), nullable=True
    )

    daily_log: Mapped["DailyLog"] = relationship(
        "DailyLog", back_populates="equipment"
    )

    __table_args__ = (
        Index("ix_log_equipment_daily_log_id", "daily_log_id"),
        Index("ix_log_equipment_type", "equipment_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<LogEquipment {self.equipment_name!r} "
            f"hours={self.hours_used} condition={self.equipment_condition!r}>"
        )


# ── Safety ────────────────────────────────────────────────────────────────────

class LogSafetyIncident(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A safety incident recorded on site today.

    Maps to ConstructionDailyLog.safety.incidents[].
    OSHA compliance and analytics make this one of the most critical tables.
    Normalized to support:
        "All OSHA-recordable incidents in the last 12 months"
        "Near-miss frequency by project"
        "Workers' comp claim preparation: incident records with OSHA fields"
    """

    __tablename__ = "log_safety_incidents"

    daily_log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_logs.id", ondelete="CASCADE"),
        nullable=False,
    )
    incident_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="first_aid | medical_treatment | lost_time_injury | near_miss | "
            "property_damage | environmental | equipment_damage",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Full incident description. OSHA 301 requires detailed description.",
    )
    worker_involved: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    time_of_incident: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="Approximate time. e.g., '10:30 AM'",
    )
    body_part_affected: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    osha_recordable: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        doc="True if this meets OSHA 300 log recordability criteria. "
            "Sprint 14 will auto-populate OSHA 300/301 from this field.",
    )
    medical_treatment_required: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True
    )
    incident_reported_to: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        doc="Who was notified. e.g., 'Site supervisor, insurance carrier'",
    )
    corrective_actions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    daily_log: Mapped["DailyLog"] = relationship(
        "DailyLog", back_populates="safety_incidents"
    )

    __table_args__ = (
        Index("ix_log_safety_incidents_daily_log_id", "daily_log_id"),
        Index("ix_log_safety_incidents_type", "incident_type"),
        Index("ix_log_safety_incidents_osha", "osha_recordable"),
    )

    def __repr__(self) -> str:
        return (
            f"<LogSafetyIncident type={self.incident_type!r} "
            f"osha={self.osha_recordable}>"
        )


class LogHazard(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A safety hazard identified on site today.

    Maps to ConstructionDailyLog.safety.hazards_identified[].
    Normalized to support:
        "All high/critical unresolved hazards across active projects"
        "Fall risk frequency analysis by project stage"
        "Safety toolbox talk data: what hazards require tomorrow's discussion?"
    """

    __tablename__ = "log_hazards"

    daily_log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_logs.id", ondelete="CASCADE"),
        nullable=False,
    )
    hazard_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="OSHA hazard category: fall_risk | struck_by | caught_between | "
            "electrical_hazard | chemical_hazard | fire_hazard | "
            "heat_or_cold_stress | noise_hazard | silica_dust | trip_hazard | other",
    )
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        doc="low | medium | high | critical",
    )
    corrective_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    corrective_action_completed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    daily_log: Mapped["DailyLog"] = relationship(
        "DailyLog", back_populates="hazards"
    )

    __table_args__ = (
        Index("ix_log_hazards_daily_log_id", "daily_log_id"),
        Index("ix_log_hazards_severity", "severity"),
        Index("ix_log_hazards_type", "hazard_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<LogHazard type={self.hazard_type!r} "
            f"severity={self.severity!r} "
            f"resolved={self.corrective_action_completed}>"
        )


# ── Delays ────────────────────────────────────────────────────────────────────

class LogDelay(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A production delay recorded today.

    Maps to ConstructionDailyLog.delays[].
    Normalized to support:
        "Total days lost to material shortage delays in Q2"
        "Subcontractor delay frequency by project"
        "Which delay types most impact critical path? (Sprint 11 scheduling)"
    """

    __tablename__ = "log_delays"

    daily_log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_logs.id", ondelete="CASCADE"),
        nullable=False,
    )
    delay_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Category: weather | material_shortage | material_delivery_late | "
            "labor_shortage | equipment_breakdown | inspection_failure | "
            "waiting_for_inspection | design_change | rework_required | "
            "permit_issue | client_decision_pending | subcontractor_delay | "
            "utility_conflict | unforeseen_site_condition | access_issue | other",
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    hours_lost: Mapped[Optional[float]] = mapped_column(Numeric(6, 2), nullable=True)
    workers_affected: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tasks_affected: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        doc="Array of task description strings affected by this delay.",
    )
    schedule_impact: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="no_impact | minor_impact | moderate_impact | major_impact | critical_path_impacted",
    )
    days_lost_to_schedule: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 2), nullable=True
    )
    resolution_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delay_resolved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    responsible_party: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        doc="Who is responsible. Important for contract claims documentation.",
    )

    daily_log: Mapped["DailyLog"] = relationship(
        "DailyLog", back_populates="delays"
    )

    __table_args__ = (
        Index("ix_log_delays_daily_log_id", "daily_log_id"),
        Index("ix_log_delays_type", "delay_type"),
        Index("ix_log_delays_schedule_impact", "schedule_impact"),
    )

    def __repr__(self) -> str:
        return (
            f"<LogDelay type={self.delay_type!r} "
            f"hours_lost={self.hours_lost} "
            f"impact={self.schedule_impact!r}>"
        )


# ── Inspections ───────────────────────────────────────────────────────────────

class LogInspection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A formal inspection that occurred or was scheduled today.

    Maps to ConstructionDailyLog.inspections[].
    Normalized to support:
        "All failed inspections with uncorrected items"
        "Inspection pass/fail rates by type across all projects"
        "Re-inspection scheduling: which projects have open correction items?"
    The corrections_required array is stored as JSON because:
        - Individual correction items are never queried independently.
        - They are always displayed and processed as a complete list.
        - A further normalization (log_inspection_corrections table) would
          add a join without providing query value at this stage.
    """

    __tablename__ = "log_inspections"

    daily_log_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_logs.id", ondelete="CASCADE"),
        nullable=False,
    )
    inspection_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="pre_pour_foundation | footing | slab | framing | rough_electrical | "
            "rough_plumbing | rough_hvac | insulation | drywall | energy_code | "
            "fire_protection | structural_special | final | certificate_of_occupancy | other",
    )
    inspector_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    inspection_authority: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        doc="e.g., 'City of Austin Building Department'",
    )
    inspection_time: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="Time of inspection. e.g., '9:30 AM'",
    )
    result: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        doc="passed | failed | conditional_pass | partial_pass | "
            "cancelled | rescheduled | pending",
    )
    corrections_required: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        doc="Array of correction items. Each item: {item_description, code_reference, "
            "severity, correction_deadline, corrected}. Stored as JSON — correction "
            "items are always processed as a complete list, never queried individually.",
    )
    next_inspection_date: Mapped[Optional[date_type]] = mapped_column(
        Date, nullable=True
    )
    inspection_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    daily_log: Mapped["DailyLog"] = relationship(
        "DailyLog", back_populates="inspections"
    )

    __table_args__ = (
        Index("ix_log_inspections_daily_log_id", "daily_log_id"),
        Index("ix_log_inspections_type", "inspection_type"),
        Index("ix_log_inspections_result", "result"),
    )

    def __repr__(self) -> str:
        return (
            f"<LogInspection type={self.inspection_type!r} "
            f"result={self.result!r}>"
        )
