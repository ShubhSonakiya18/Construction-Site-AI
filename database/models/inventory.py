"""
database/models/inventory.py — InventoryItem and PurchaseOrder: Sprint 12.

Two tables giving materials the persistent, cross-log identity they
never had: log_materials_used / log_materials_delivered / log_materials_required
(Sprint 6, frozen) are per-log line items with no running quantity across
time — two different daily logs both mentioning "Cement bags" are three
unrelated rows today, because nothing tracks how much cement the project
actually has on hand. This is the same gap Sprint 11 closed for
construction stages (no persistent per-project schedule existed either),
solved the same way: a real table, reconciled from approved daily logs
rather than replacing what those logs already record.

    inventory_items — one row per distinct material PER PROJECT (not
        global across companies/projects — "Cement bags" on Project A and
        Project B are different rows with independent quantities, matching
        how LogMaterialUsed is already scoped per log per project).
        Created on first mention (by Deliverable 2's reconciliation step)
        rather than requiring a separate "register a material" step.

    purchase_orders — one row per order, human-initiated or auto-generated
        when quantity_on_hand drops to/below reorder_point (Deliverable 3).
        An auto-generated PO is always created as status="draft" — a
        suggestion, never an order actually placed; no code path in this
        sprint transmits anything to a real supplier (Deliverable 6 is
        explicitly preparation only, per docs/NEXT_SPRINT.md).

preferred_supplier / purchase_orders.supplier are plain strings, matching
LogMaterialUsed.supplier's existing shape — not a normalized `suppliers`
table. Documented, conscious denormalization (same reasoning
database/models/project.py's client_name docstring already uses): worth
revisiting only if a concrete need for shared supplier records surfaces
during implementation, not built speculatively up front.

LogMaterialDelivered.purchase_order_number (database/models/log_items.py)
is a plain nullable string column with no FK constraint, unused by
anything until now. This migration does NOT add a FK constraint from it
to purchase_orders.id — same reasoning as Sprint 11's
LogWorkItem.linked_schedule_task_id decision: existing rows predate this
table and have no reliable value to backfill/match against. The link
stays soft.
"""
from __future__ import annotations

import uuid
from datetime import date as date_type, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base
from database.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from database.models.project import Project


class InventoryItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One material's running quantity for one project.

    Sprint 12 scope: project-scoped, not global — see module docstring.
    No SoftDeleteMixin: an inventory item with zero quantity is still a
    real, meaningful record (this project has tracked this material and
    currently has none) — deleting it would lose reorder-point/lead-time
    configuration a project manager set deliberately. A material that
    turns out to be a duplicate/mistake is a data-correction case, not a
    routine soft-delete case, matching how reference data
    (Trade/ConstructionStage) also has no soft delete.
    """

    __tablename__ = "inventory_items"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    material_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Matches LogMaterialUsed.material_name's shape/length — the "
            "same string a foreman's voice recording would produce, not a "
            "separately-normalized catalog name.",
    )
    category: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        doc="Material category code matching MaterialCategory.code, same "
            "as LogMaterialUsed.category.",
    )
    unit: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="e.g. 'bags', 'linear_feet', 'cubic_yards' — matches "
            "LogMaterialUsed.unit's shape.",
    )
    quantity_on_hand: Mapped[float] = mapped_column(
        Numeric(12, 3),
        nullable=False,
        default=0,
        doc="Running quantity, reconciled from approved daily logs' "
            "materials_used (decrements) and materials_delivered "
            "(increments) — see app/services/inventory_service.py's "
            "reconciliation logic (Deliverable 2). Never edited directly "
            "by a user; it is a computed ledger, not a manual counter.",
    )
    reorder_point: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 3),
        nullable=True,
        doc="quantity_on_hand at or below this value triggers an "
            "auto-generated draft purchase order (Deliverable 3). NULL "
            "means auto-reorder is not configured for this item — it "
            "still tracks quantity, it just never auto-suggests a PO.",
    )
    typical_lead_time_days: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        doc="Days between placing an order and delivery arriving — the "
            "input to Deliverable 4's lead-time warnings. NULL means no "
            "lead-time warning is ever computed for this item.",
    )
    preferred_supplier: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        doc="Plain string, not a FK to a suppliers table — see module "
            "docstring for why.",
    )
    applicable_stage_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        doc="Matches a node id in knowledge/dependency_graph.json / a "
            "ScheduleTask.stage_id (e.g. 'foundation') — the stage this "
            "material is needed for, used by Deliverable 4 to cross-"
            "reference against the project's schedule. NULL means no "
            "lead-time warning is computed (same effect as "
            "typical_lead_time_days being NULL). Not a FK for the same "
            "reason ScheduleTask.stage_id isn't one — dependency_graph.json "
            "is a static knowledge file (ADR-006), not a database table.",
    )
    last_counted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When quantity_on_hand was last confirmed against reality "
            "(a log-driven reconciliation, or a future manual count "
            "feature) — NULL means it has only ever been inferred from "
            "log reconciliation, never independently verified.",
    )

    project: Mapped["Project"] = relationship("Project", back_populates="inventory_items")
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(
        "PurchaseOrder",
        back_populates="inventory_item",
        cascade="all, delete-orphan",
        order_by="PurchaseOrder.created_at.desc()",
    )

    __table_args__ = (
        Index("ix_inventory_items_project_id", "project_id"),
        UniqueConstraint(
            "project_id", "material_name",
            name="uq_inventory_items_project_material",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<InventoryItem material_name={self.material_name!r} "
            f"qty={self.quantity_on_hand} project_id={self.project_id}>"
        )


class PurchaseOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One purchase order — human-initiated or auto-generated.

    No SoftDeleteMixin: status="cancelled" IS the "this didn't happen"
    state for a PO — a second delete mechanism would be redundant and
    ambiguous (is a cancelled-and-deleted PO different from a merely
    cancelled one?). Matches AuditLog's "cancel via status, don't hide
    via delete" pattern used for a similar record-of-what-happened case.
    """

    __tablename__ = "purchase_orders"

    inventory_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        doc="draft | submitted | delivered | cancelled. draft = "
            "system-suggested or human-created but not yet acted on; "
            "submitted = a human confirmed placing the order (still no "
            "real supplier transmission — Deliverable 6 is preparation "
            "only); delivered = matched against a later "
            "LogMaterialDelivered event or marked manually; cancelled = "
            "the record-of-what-happened terminal state, see class doc.",
    )
    quantity_ordered: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    unit_cost_usd: Mapped[Optional[float]] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    supplier: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        doc="Plain string, matching LogMaterialDelivered.supplier's shape "
            "— see module docstring on why there is no suppliers table.",
    )
    auto_generated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="True if Deliverable 3's reorder-point check created this row; "
            "False if a human created it directly via "
            "POST /projects/{id}/inventory/{item_id}/purchase-orders.",
    )
    ordered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When status moved to 'submitted'. NULL while still 'draft'.",
    )
    expected_delivery_date: Mapped[Optional[date_type]] = mapped_column(
        Date, nullable=True
    )
    actual_delivery_date: Mapped[Optional[date_type]] = mapped_column(
        Date, nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    inventory_item: Mapped["InventoryItem"] = relationship(
        "InventoryItem", back_populates="purchase_orders"
    )

    __table_args__ = (
        Index("ix_purchase_orders_inventory_item_id", "inventory_item_id"),
        Index("ix_purchase_orders_status", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<PurchaseOrder status={self.status!r} "
            f"qty={self.quantity_ordered} auto={self.auto_generated}>"
        )
