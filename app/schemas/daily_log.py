"""
app/schemas/daily_log.py — Request/response models for the daily-logs resource.

Read models use model_config = ConfigDict(from_attributes=True) so a route
can return `DailyLogRead.model_validate(orm_instance)` directly — Pydantic
reads attributes off the SQLAlchemy object rather than requiring a dict.

Field selection: each *Read model exposes the fields a client actually
needs, not the full ORM column set. TimestampMixin's created_at/updated_at
are included where useful for the client (e.g. "when was this logged");
internal audit columns (created_by_id/updated_by_id) are included as plain
UUID strings since Sprint 7 clients need to know who created a record.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Child table read models (one per normalized child, see database/models/log_items.py) ──

class TradeOnSiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    trade: str
    workers_count: int
    foreman_name: Optional[str] = None
    subcontractor_company: Optional[str] = None
    hours_worked: Optional[float] = None
    notes: Optional[str] = None


class WorkItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    task_description: str
    trade: str
    location_on_site: Optional[str] = None
    quantity_completed: Optional[float] = None
    unit_of_measure: Optional[str] = None
    task_completion_percent: Optional[float] = None
    notes: Optional[str] = None


class WorkInProgressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    task_description: str
    trade: Optional[str] = None
    location_on_site: Optional[str] = None
    current_completion_percent: Optional[float] = None
    expected_completion_date: Optional[date] = None
    blocking_issues: Optional[str] = None


class MaterialUsedRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    material_name: str
    category: Optional[str] = None
    quantity_used: float
    unit: str
    waste_quantity: Optional[float] = None
    unit_cost_usd: Optional[float] = None
    supplier: Optional[str] = None


class MaterialDeliveredRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    material_name: str
    quantity_delivered: float
    unit: str
    supplier: Optional[str] = None
    delivery_condition: Optional[str] = None
    purchase_order_number: Optional[str] = None


class MaterialRequiredRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    material_name: str
    quantity_needed: float
    unit: str
    urgency: str
    notes: Optional[str] = None


class EquipmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    equipment_name: str
    equipment_type: Optional[str] = None
    is_rented: Optional[bool] = None
    hours_used: Optional[float] = None
    operator: Optional[str] = None
    equipment_condition: Optional[str] = None
    maintenance_issues: Optional[str] = None


class SafetyIncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    incident_type: str
    description: str
    worker_involved: Optional[str] = None
    osha_recordable: Optional[bool] = None
    medical_treatment_required: Optional[bool] = None
    corrective_actions: Optional[str] = None


class HazardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    hazard_type: str
    location: Optional[str] = None
    description: str
    severity: str
    corrective_action: Optional[str] = None
    corrective_action_completed: bool


class DelayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    delay_type: str
    description: str
    hours_lost: Optional[float] = None
    workers_affected: Optional[int] = None
    schedule_impact: Optional[str] = None
    days_lost_to_schedule: Optional[float] = None
    delay_resolved: bool
    responsible_party: Optional[str] = None


class InspectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    inspection_type: str
    inspector_name: Optional[str] = None
    inspection_authority: Optional[str] = None
    result: str
    inspection_notes: Optional[str] = None


# ── DailyLog itself ────────────────────────────────────────────────────────────

class DailyLogSummary(BaseModel):
    """Compact shape for list endpoints (GET /projects/{id}/daily-logs) —
    no child tables, so listing 30 logs stays a light query and payload."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    site_id: Optional[UUID] = None
    log_date: date
    current_stage: str
    review_status: str
    total_workers_present: int
    overall_project_completion_percent: Optional[float] = None
    created_at: datetime


class DailyLogRead(DailyLogSummary):
    """Full shape for GET /daily-logs/{id} — includes every normalized
    child table, matching DailyLogRepository.get_with_children()."""

    foreman_id: Optional[UUID] = None
    log_source: str
    review_notes: Optional[str] = None
    reviewed_by_id: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    raw_transcript: Optional[str] = None
    transcript_confidence: Optional[float] = None
    stage_completion_percent: Optional[float] = None
    weather: Optional[dict] = None
    total_workers_scheduled: Optional[int] = None
    total_man_hours_worked: Optional[float] = None
    safety_meeting_conducted: bool
    safety_notes: Optional[str] = None
    tomorrow_plan: Optional[dict] = None
    client_communication: Optional[dict] = None

    trades_on_site: list[TradeOnSiteRead] = Field(default_factory=list)
    work_items: list[WorkItemRead] = Field(default_factory=list)
    work_in_progress: list[WorkInProgressRead] = Field(default_factory=list)
    materials_used: list[MaterialUsedRead] = Field(default_factory=list)
    materials_delivered: list[MaterialDeliveredRead] = Field(default_factory=list)
    materials_required: list[MaterialRequiredRead] = Field(default_factory=list)
    equipment: list[EquipmentRead] = Field(default_factory=list)
    safety_incidents: list[SafetyIncidentRead] = Field(default_factory=list)
    hazards: list[HazardRead] = Field(default_factory=list)
    delays: list[DelayRead] = Field(default_factory=list)
    inspections: list[InspectionRead] = Field(default_factory=list)


# ── Review lifecycle request bodies ───────────────────────────────────────────

class ApproveLogRequest(BaseModel):
    notes: Optional[str] = None


class RejectLogRequest(BaseModel):
    notes: str = Field(..., min_length=1, description="Required: why this log was rejected.")
