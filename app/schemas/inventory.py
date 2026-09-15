"""app/schemas/inventory.py — Request/response models for the inventory
and purchase-order resources. Sprint 12."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PurchaseOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    inventory_item_id: UUID
    status: str
    quantity_ordered: float
    unit_cost_usd: Optional[float] = None
    supplier: Optional[str] = None
    auto_generated: bool
    ordered_at: Optional[datetime] = None
    expected_delivery_date: Optional[date] = None
    actual_delivery_date: Optional[date] = None
    notes: Optional[str] = None
    created_at: datetime


class LeadTimeWarningRead(BaseModel):
    """One inventory item's lead-time warning — pure date arithmetic
    (see ADR-048 / app/services/inventory_service.py), not AI-generated
    text, matching Sprint 11's variance/delay-impact fields."""

    material_name: str
    stage_id: str
    status: str
    days_until_stage_start: Optional[int] = None
    order_by_date: Optional[date] = None
    message: str


class InventoryItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    material_name: str
    category: Optional[str] = None
    unit: str
    quantity_on_hand: float
    reorder_point: Optional[float] = None
    typical_lead_time_days: Optional[int] = None
    preferred_supplier: Optional[str] = None
    applicable_stage_id: Optional[str] = None
    last_counted_at: Optional[datetime] = None
    purchase_orders: list[PurchaseOrderRead] = Field(default_factory=list)


class ProjectInventoryResponseData(BaseModel):
    """Response for GET /projects/{id}/inventory — Sprint 12. Includes
    lead-time warnings inline (Deliverable 4), computed at read time
    from the project's current inventory + schedule state — never
    persisted, same pattern as Sprint 11's ProjectScheduleResponseData."""

    project_id: UUID
    items: list[InventoryItemRead]
    lead_time_warnings: list[LeadTimeWarningRead]


class CreatePurchaseOrderRequest(BaseModel):
    """Body for POST /projects/{id}/inventory/{item_id}/purchase-orders
    — the human-initiated counterpart to Deliverable 3's auto-generated
    path. Always creates status="draft"; use the status-update endpoint
    to move it to "submitted"."""

    quantity_ordered: float = Field(gt=0)
    supplier: Optional[str] = None
    unit_cost_usd: Optional[float] = Field(default=None, ge=0)


class UpdatePurchaseOrderStatusRequest(BaseModel):
    """Body for PATCH .../purchase-orders/{po_id}. Only the status
    transition is exposed here — quantity/supplier corrections go
    through creating a new PO, matching how this codebase treats a
    purchase order as a record of what happened rather than a freely
    editable draft once created (see PurchaseOrder's class docstring on
    why cancellation is a status, not a delete)."""

    status: str = Field(pattern="^(draft|submitted|delivered|cancelled)$")
