"""
database/repositories/inventory.py — InventoryItem / PurchaseOrder repository.

Sprint 12. Tenant scoping matches ScheduleRepository's pattern exactly:
InventoryItem has no direct company_id column — company is reached via
project_id -> Project.company_id, so every scoped method joins through
Project the same way ScheduleRepository's methods do. PurchaseOrder scopes
one hop further, through its parent InventoryItem's project.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from database.models.inventory import InventoryItem, PurchaseOrder
from database.models.project import Project
from database.repositories.tenant import TenantContext, TenantScopedRepository

# Default restock multiple when auto-generating a draft PO at reorder
# point — see docs/DECISIONS.md's Sprint 12 ADR on why a flat multiple
# was chosen over a consumption-rate-driven formula for this sprint.
_AUTO_REORDER_MULTIPLE = 2


class InventoryRepository(TenantScopedRepository[InventoryItem]):
    """Repository for InventoryItem and its PurchaseOrder children."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, InventoryItem)

    # ── Read ──────────────────────────────────────────────────────────────────

    def list_for_project_scoped(
        self, project_id: UUID, *, tenant: TenantContext
    ) -> list[InventoryItem]:
        """Tenant-safe list of a project's inventory + each item's
        purchase orders. Returns an empty list for both "no items yet"
        and "project belongs to a different company" — the router
        distinguishes those cases by checking the project itself exists
        first (see app/api/v1/projects.py), matching how
        ScheduleRepository's read path is structured."""
        stmt = (
            select(InventoryItem)
            .join(Project, InventoryItem.project_id == Project.id)
            .where(InventoryItem.project_id == project_id)
            .where(Project.company_id == tenant.company_id)
            .options(selectinload(InventoryItem.purchase_orders))
            .order_by(InventoryItem.material_name)
        )
        return list(self._session.execute(stmt).scalars().all())

    def get_item_scoped(
        self, project_id: UUID, item_id: UUID, *, tenant: TenantContext
    ) -> Optional[InventoryItem]:
        """Tenant-safe read of a single inventory item, scoped through
        its project. Same indistinguishable-404 pattern every other
        *_scoped() method in this codebase uses."""
        stmt = (
            select(InventoryItem)
            .join(Project, InventoryItem.project_id == Project.id)
            .where(InventoryItem.id == item_id)
            .where(InventoryItem.project_id == project_id)
            .where(Project.company_id == tenant.company_id)
            .options(selectinload(InventoryItem.purchase_orders))
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_or_create_item(
        self,
        project_id: UUID,
        *,
        material_name: str,
        unit: str,
        category: Optional[str] = None,
    ) -> InventoryItem:
        """Return the existing InventoryItem for this (project,
        material_name), or create one at quantity_on_hand=0 if this is
        the first time this material has been mentioned for this
        project. Deliberately NOT tenant-scoped by a TenantContext
        parameter — this is called from
        record_material_consumption_from_log(), which already resolves
        its project_id from a tenant-scoped DailyLog lookup one level up
        (app/api/v1/daily_logs.py's approve_log()), the same way
        ScheduleRepository.record_actual_progress()'s own call site
        already has a tenant-verified project_id in hand before calling
        in. Matches the "no separate registration step" design in
        docs/NEXT_SPRINT.md's Deliverable 2.
        """
        stmt = select(InventoryItem).where(
            InventoryItem.project_id == project_id,
            InventoryItem.material_name == material_name,
        )
        existing = self._session.execute(stmt).scalar_one_or_none()
        if existing is not None:
            return existing

        item = InventoryItem(
            project_id=project_id,
            material_name=material_name,
            unit=unit,
            category=category,
            quantity_on_hand=0,
        )
        self._session.add(item)
        self._session.flush()
        return item

    # ── Update (Deliverable 2 + 3) ───────────────────────────────────────────

    def record_material_consumption_from_log(
        self, project_id: UUID, *, materials_used: list, materials_delivered: list
    ) -> list[InventoryItem]:
        """Sprint 12, Deliverable 2: reconcile inventory from one
        approved daily log's materials_used (decrement) and
        materials_delivered (increment) child rows.

        Called from the same approval hook Sprint 11's Deliverable 4
        (record_actual_progress) attached to POST /daily-logs/{id}/approve
        — fully isolated from both the approval itself and from the
        schedule update, matching the transaction-isolation fix
        documented in docs/DECISIONS.md's Sprint 11 Known Bugs #3: this
        method's caller commits the approval first, then attempts
        reconciliation in its own transaction, so a reconciliation
        failure can never undo an approval the response already
        promised succeeded.

        materials_used / materials_delivered are the ORM child rows
        themselves (LogMaterialUsed / LogMaterialDelivered instances),
        not the extraction-shaped dicts — this runs against the
        already-persisted DailyLog, unlike _rebuild_extracted_log()
        which reconstructs dicts for the generation services.

        Returns the list of InventoryItems touched, so the caller (and
        Deliverable 3's reorder check, run immediately after this by the
        same call site) knows which items to check against
        reorder_point without re-querying every item for the project.
        """
        touched: list[InventoryItem] = []

        for used in materials_used:
            item = self.get_or_create_item(
                project_id,
                material_name=used.material_name,
                unit=used.unit,
                category=used.category,
            )
            item.quantity_on_hand = float(item.quantity_on_hand) - float(used.quantity_used)
            touched.append(item)

        for delivered in materials_delivered:
            item = self.get_or_create_item(
                project_id,
                material_name=delivered.material_name,
                unit=delivered.unit,
            )
            item.quantity_on_hand = float(item.quantity_on_hand) + float(delivered.quantity_delivered)
            if item not in touched:
                touched.append(item)

        self._session.flush()
        return touched

    def check_and_create_reorder_purchase_orders(
        self, items: list[InventoryItem]
    ) -> list[PurchaseOrder]:
        """Sprint 12, Deliverable 3: for each item at or below its
        reorder_point, create a draft, auto-generated purchase order —
        a suggestion only, never an order actually placed (see
        database/models/inventory.py's PurchaseOrder.status doc).

        Skips items with reorder_point unset (auto-reorder not
        configured) and items that already have an open (draft or
        submitted) auto-generated PO, so repeated approvals of logs
        that keep consuming the same low-stock material don't pile up
        duplicate suggestions — one open draft per item is enough for a
        human to act on.
        """
        created: list[PurchaseOrder] = []
        for item in items:
            if item.reorder_point is None:
                continue
            if float(item.quantity_on_hand) > float(item.reorder_point):
                continue

            has_open_auto_po = any(
                po.auto_generated and po.status in ("draft", "submitted")
                for po in item.purchase_orders
            )
            if has_open_auto_po:
                continue

            po = PurchaseOrder(
                inventory_item_id=item.id,
                status="draft",
                quantity_ordered=float(item.reorder_point) * _AUTO_REORDER_MULTIPLE,
                supplier=item.preferred_supplier,
                auto_generated=True,
            )
            self._session.add(po)
            created.append(po)

        if created:
            self._session.flush()
        return created

    def create_purchase_order(
        self,
        project_id: UUID,
        item_id: UUID,
        *,
        quantity_ordered: float,
        supplier: Optional[str],
        unit_cost_usd: Optional[float],
        tenant: TenantContext,
    ) -> Optional[PurchaseOrder]:
        """Human-initiated PO creation — the manual counterpart to
        check_and_create_reorder_purchase_orders(). Returns None if the
        item doesn't belong to this tenant/project (same 404-not-403
        pattern as every other tenant-scoped write)."""
        item = self.get_item_scoped(project_id, item_id, tenant=tenant)
        if item is None:
            return None

        po = PurchaseOrder(
            inventory_item_id=item.id,
            status="draft",
            quantity_ordered=quantity_ordered,
            supplier=supplier,
            unit_cost_usd=unit_cost_usd,
            auto_generated=False,
        )
        self._session.add(po)
        self._session.flush()
        return po

    def update_purchase_order_status_scoped(
        self,
        project_id: UUID,
        item_id: UUID,
        po_id: UUID,
        *,
        status: str,
        tenant: TenantContext,
    ) -> Optional[PurchaseOrder]:
        """Transition a purchase order's status. Setting status to
        'submitted' also stamps ordered_at (first transition only — a
        second call with status='submitted' on an already-submitted PO
        is idempotent, matching record_actual_progress()'s idempotency
        pattern for repeated calls)."""
        from datetime import datetime, timezone

        item = self.get_item_scoped(project_id, item_id, tenant=tenant)
        if item is None:
            return None

        po = next((p for p in item.purchase_orders if p.id == po_id), None)
        if po is None:
            return None

        po.status = status
        if status == "submitted" and po.ordered_at is None:
            po.ordered_at = datetime.now(timezone.utc)

        self._session.flush()
        return po
