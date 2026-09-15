"""
tests/test_api_inventory.py — Sprint 12: GET/POST /projects/{id}/inventory,
purchase-order endpoints, and the Deliverable 2/3 reconciliation hook on
POST /daily-logs/{id}/approve.

Same two-company tenant-isolation pattern every Sprint 9-11 API test file
uses (test_api_analytics.py, test_api_schedule.py, ...).
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from database.models.company import Company
from database.models.daily_log import DailyLog
from database.models.inventory import InventoryItem, PurchaseOrder
from database.models.log_items import LogMaterialDelivered, LogMaterialUsed
from database.models.project import Project
from database.seed.sample_data import PROJECT_ID

pytest_plugins = ["tests.conftest_api"]

INVENTORY_URL = f"/api/v1/projects/{PROJECT_ID}/inventory"


def test_get_requires_authentication(api_client):
    response = api_client.get(INVENTORY_URL)
    assert response.status_code == 401


def test_get_unknown_project_is_404(api_client, auth_headers):
    response = api_client.get(
        f"/api/v1/projects/{uuid.uuid4()}/inventory", headers=auth_headers
    )
    assert response.status_code == 404


def test_get_empty_inventory_returns_200_with_empty_list(api_client, auth_headers):
    """No log has been approved yet for the seeded project's inventory
    (distinct from the schedule -- inventory starts genuinely empty,
    there's no seeding step, matching Deliverable 2's "created on first
    mention" design)."""
    response = api_client.get(INVENTORY_URL, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["items"] == []
    assert body["lead_time_warnings"] == []


class TestReconciliationOnApproval:
    """Sprint 12 Deliverables 2 + 3: approving a log with
    materials_used/materials_delivered reconciles InventoryItem rows,
    and dropping to/below reorder_point auto-creates a draft PO."""

    @pytest.fixture
    def draft_log_with_materials(self, seeded_session):
        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 9, 20), current_stage="foundation",
            review_status="under_review", total_workers_present=4,
        )
        seeded_session.add(log)
        seeded_session.flush()
        seeded_session.add(LogMaterialUsed(
            daily_log_id=log.id, material_name="Cement bags",
            quantity_used=30.0, unit="bags",
        ))
        seeded_session.add(LogMaterialDelivered(
            daily_log_id=log.id, material_name="Rebar",
            quantity_delivered=50.0, unit="pieces",
        ))
        seeded_session.commit()
        return log

    def test_approving_creates_inventory_items_from_materials(
        self, api_client, auth_headers, draft_log_with_materials, seeded_session
    ):
        response = api_client.post(
            f"/api/v1/daily-logs/{draft_log_with_materials.id}/approve",
            headers=auth_headers, json={},
        )
        assert response.status_code == 200, response.text

        seeded_session.expire_all()
        cement = (
            seeded_session.query(InventoryItem)
            .filter(InventoryItem.project_id == PROJECT_ID,
                    InventoryItem.material_name == "Cement bags")
            .one()
        )
        # Used (consumed) -> decrements from a starting 0.
        assert float(cement.quantity_on_hand) == -30.0

        rebar = (
            seeded_session.query(InventoryItem)
            .filter(InventoryItem.project_id == PROJECT_ID,
                    InventoryItem.material_name == "Rebar")
            .one()
        )
        # Delivered -> increments from a starting 0.
        assert float(rebar.quantity_on_hand) == 50.0

    def test_approval_still_succeeds_with_no_materials(self, api_client, auth_headers, seeded_session):
        """The approval itself must never fail just because a log has no
        materials rows -- reconciliation is best-effort, not a
        precondition (mirrors Sprint 11's schedule-hook test)."""
        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 9, 21), current_stage="foundation",
            review_status="under_review", total_workers_present=4,
        )
        seeded_session.add(log)
        seeded_session.commit()

        response = api_client.post(
            f"/api/v1/daily-logs/{log.id}/approve", headers=auth_headers, json={},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["review_status"] == "approved"

    def test_dropping_to_reorder_point_creates_draft_po(
        self, api_client, auth_headers, seeded_session
    ):
        item = InventoryItem(
            project_id=PROJECT_ID, material_name="Plywood sheets",
            unit="sheets", quantity_on_hand=15, reorder_point=10,
        )
        seeded_session.add(item)
        seeded_session.commit()
        item_id = item.id

        log = DailyLog(
            id=uuid.uuid4(), project_id=PROJECT_ID,
            log_date=date(2026, 9, 22), current_stage="framing",
            review_status="under_review", total_workers_present=4,
        )
        seeded_session.add(log)
        seeded_session.flush()
        seeded_session.add(LogMaterialUsed(
            daily_log_id=log.id, material_name="Plywood sheets",
            quantity_used=8.0, unit="sheets",
        ))
        seeded_session.commit()

        response = api_client.post(
            f"/api/v1/daily-logs/{log.id}/approve", headers=auth_headers, json={},
        )
        assert response.status_code == 200

        seeded_session.expire_all()
        pos = (
            seeded_session.query(PurchaseOrder)
            .filter(PurchaseOrder.inventory_item_id == item_id)
            .all()
        )
        assert len(pos) == 1
        assert pos[0].status == "draft"
        assert pos[0].auto_generated is True

    def test_second_approval_does_not_duplicate_open_auto_po(
        self, api_client, auth_headers, seeded_session
    ):
        """Repeated approvals of logs that keep consuming a low-stock
        material must not pile up duplicate auto-generated suggestions
        while one is already open."""
        item = InventoryItem(
            project_id=PROJECT_ID, material_name="Steel rods",
            unit="rods", quantity_on_hand=5, reorder_point=10,
        )
        seeded_session.add(item)
        seeded_session.commit()
        item_id = item.id

        for i, d in enumerate([date(2026, 9, 23), date(2026, 9, 24)]):
            log = DailyLog(
                id=uuid.uuid4(), project_id=PROJECT_ID,
                log_date=d, current_stage="framing",
                review_status="under_review", total_workers_present=4,
            )
            seeded_session.add(log)
            seeded_session.flush()
            seeded_session.add(LogMaterialUsed(
                daily_log_id=log.id, material_name="Steel rods",
                quantity_used=1.0, unit="rods",
            ))
            seeded_session.commit()
            response = api_client.post(
                f"/api/v1/daily-logs/{log.id}/approve", headers=auth_headers, json={},
            )
            assert response.status_code == 200

        seeded_session.expire_all()
        pos = (
            seeded_session.query(PurchaseOrder)
            .filter(PurchaseOrder.inventory_item_id == item_id)
            .all()
        )
        assert len(pos) == 1


class TestPurchaseOrderEndpoints:
    @pytest.fixture
    def inventory_item(self, seeded_session):
        item = InventoryItem(
            project_id=PROJECT_ID, material_name="Insulation batts",
            unit="rolls", quantity_on_hand=20,
        )
        seeded_session.add(item)
        seeded_session.commit()
        return item

    def test_create_purchase_order(self, api_client, auth_headers, inventory_item):
        response = api_client.post(
            f"/api/v1/projects/{PROJECT_ID}/inventory/{inventory_item.id}/purchase-orders",
            headers=auth_headers,
            json={"quantity_ordered": 40, "supplier": "ABC Supply"},
        )
        assert response.status_code == 201, response.text
        body = response.json()["data"]
        assert body["status"] == "draft"
        assert body["auto_generated"] is False
        assert body["quantity_ordered"] == 40

    def test_create_purchase_order_unknown_item_is_404(self, api_client, auth_headers):
        response = api_client.post(
            f"/api/v1/projects/{PROJECT_ID}/inventory/{uuid.uuid4()}/purchase-orders",
            headers=auth_headers, json={"quantity_ordered": 10},
        )
        assert response.status_code == 404

    def test_update_status_to_submitted_stamps_ordered_at(
        self, api_client, auth_headers, inventory_item
    ):
        create = api_client.post(
            f"/api/v1/projects/{PROJECT_ID}/inventory/{inventory_item.id}/purchase-orders",
            headers=auth_headers, json={"quantity_ordered": 40},
        )
        po_id = create.json()["data"]["id"]

        response = api_client.patch(
            f"/api/v1/projects/{PROJECT_ID}/inventory/{inventory_item.id}/purchase-orders/{po_id}",
            headers=auth_headers, json={"status": "submitted"},
        )
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["status"] == "submitted"
        assert body["ordered_at"] is not None

    def test_invalid_status_is_422(self, api_client, auth_headers, inventory_item):
        create = api_client.post(
            f"/api/v1/projects/{PROJECT_ID}/inventory/{inventory_item.id}/purchase-orders",
            headers=auth_headers, json={"quantity_ordered": 40},
        )
        po_id = create.json()["data"]["id"]

        response = api_client.patch(
            f"/api/v1/projects/{PROJECT_ID}/inventory/{inventory_item.id}/purchase-orders/{po_id}",
            headers=auth_headers, json={"status": "not_a_real_status"},
        )
        assert response.status_code == 422


class TestLeadTimeWarnings:
    def test_item_with_no_schedule_yet_has_no_warnings(
        self, api_client, auth_headers, seeded_session
    ):
        seeded_session.add(InventoryItem(
            project_id=PROJECT_ID, material_name="Windows",
            unit="units", quantity_on_hand=0,
            typical_lead_time_days=30, applicable_stage_id="framing",
        ))
        seeded_session.commit()

        # No schedule exists for this project in this test's isolated
        # session -- warnings require both inventory AND schedule data.
        response = api_client.get(INVENTORY_URL, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["lead_time_warnings"] == []

    def test_item_with_schedule_and_due_lead_time_produces_warning(
        self, api_client, auth_headers, seeded_session
    ):
        create_schedule = api_client.post(
            f"/api/v1/projects/{PROJECT_ID}/schedule", headers=auth_headers, json={},
        )
        assert create_schedule.status_code == 201
        tasks = create_schedule.json()["data"]["tasks"]
        framing_start = next(t for t in tasks if t["stage_id"] == "framing")["planned_start_date"]

        # Configure an item whose lead time makes "today" (test-run time)
        # almost certainly past the order-by date for a schedule seeded
        # from the project's real project_start_date (2026-03-10) --
        # framing's planned_start_date is already months in the past
        # relative to any realistic "today", so a large lead_time_days
        # guarantees the order window has passed.
        seeded_session.add(InventoryItem(
            project_id=PROJECT_ID, material_name="Windows",
            unit="units", quantity_on_hand=0,
            typical_lead_time_days=3650, applicable_stage_id="framing",
        ))
        seeded_session.commit()

        response = api_client.get(INVENTORY_URL, headers=auth_headers)
        assert response.status_code == 200
        warnings = response.json()["data"]["lead_time_warnings"]
        assert any(w["material_name"] == "Windows" for w in warnings)
        window = next(w for w in warnings if w["material_name"] == "Windows")
        assert window["stage_id"] == "framing"

    def test_submitted_po_suppresses_warning(self, api_client, auth_headers, seeded_session):
        create_schedule = api_client.post(
            f"/api/v1/projects/{PROJECT_ID}/schedule", headers=auth_headers, json={},
        )
        assert create_schedule.status_code == 201

        item = InventoryItem(
            project_id=PROJECT_ID, material_name="Windows",
            unit="units", quantity_on_hand=0,
            typical_lead_time_days=3650, applicable_stage_id="framing",
        )
        seeded_session.add(item)
        seeded_session.flush()
        seeded_session.add(PurchaseOrder(
            inventory_item_id=item.id, status="submitted",
            quantity_ordered=10,
        ))
        seeded_session.commit()

        response = api_client.get(INVENTORY_URL, headers=auth_headers)
        warnings = response.json()["data"]["lead_time_warnings"]
        assert not any(w["material_name"] == "Windows" for w in warnings)


class TestTenantIsolation:
    def test_cannot_read_another_companys_inventory(
        self, api_client, auth_headers, seeded_session
    ):
        other_company = Company(id=uuid.uuid4(), name="Other Co", slug="other-co-inventory-test")
        seeded_session.add(other_company)
        seeded_session.flush()
        other_project = Project(
            id=uuid.uuid4(), company_id=other_company.id, name="Other Project",
            status="active",
        )
        seeded_session.add(other_project)
        seeded_session.commit()

        response = api_client.get(
            f"/api/v1/projects/{other_project.id}/inventory", headers=auth_headers,
        )
        assert response.status_code == 404

    def test_cannot_create_po_for_another_companys_item(
        self, api_client, auth_headers, seeded_session
    ):
        other_company = Company(id=uuid.uuid4(), name="Other Co 2", slug="other-co-inventory-test-2")
        seeded_session.add(other_company)
        seeded_session.flush()
        other_project = Project(
            id=uuid.uuid4(), company_id=other_company.id, name="Other Project 2",
            status="active",
        )
        seeded_session.add(other_project)
        seeded_session.flush()
        other_item = InventoryItem(
            project_id=other_project.id, material_name="Secret Material",
            unit="units", quantity_on_hand=0,
        )
        seeded_session.add(other_item)
        seeded_session.commit()

        response = api_client.post(
            f"/api/v1/projects/{PROJECT_ID}/inventory/{other_item.id}/purchase-orders",
            headers=auth_headers, json={"quantity_ordered": 10},
        )
        assert response.status_code == 404
