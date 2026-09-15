"""Add inventory and procurement tables — Sprint 12

Revision ID: 006
Revises: 005
Create Date: 2026-09-16

Adds two new tables:
    inventory_items — one row per distinct material per project (unique
        on (project_id, material_name) — Sprint 12 scope is project-
        scoped inventory, not global across companies/projects; see
        database/models/inventory.py module docstring).
    purchase_orders  — one row per order, human-initiated or auto-
        generated when quantity_on_hand drops to/below reorder_point.

No existing table is modified. LogMaterialDelivered.purchase_order_number
(added in an earlier sprint's model, never in its own migration since it
was a plain unconstrained string column) is deliberately left as-is here
— this migration does not add a FK from it to purchase_orders.id. See
database/models/inventory.py's module docstring for why the link stays
soft for now (same reasoning as Sprint 11's
LogWorkItem.linked_schedule_task_id decision).

Upgrade:   Creates inventory_items and purchase_orders with their
           indexes and unique constraint.
Downgrade: Drops purchase_orders then inventory_items (child before
           parent, matching the FK direction).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inventory_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("material_name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column(
            "quantity_on_hand",
            sa.Numeric(12, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column("reorder_point", sa.Numeric(12, 3), nullable=True),
        sa.Column("typical_lead_time_days", sa.Integer(), nullable=True),
        sa.Column("preferred_supplier", sa.String(200), nullable=True),
        sa.Column("applicable_stage_id", sa.String(100), nullable=True),
        sa.Column(
            "last_counted_at", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "project_id", "material_name",
            name="uq_inventory_items_project_material",
        ),
    )
    op.create_index(
        "ix_inventory_items_project_id", "inventory_items", ["project_id"]
    )

    op.create_table(
        "purchase_orders",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "inventory_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("inventory_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="draft"
        ),
        sa.Column("quantity_ordered", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_cost_usd", sa.Numeric(12, 4), nullable=True),
        sa.Column("supplier", sa.String(200), nullable=True),
        sa.Column(
            "auto_generated",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("ordered_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
        sa.Column("actual_delivery_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_purchase_orders_inventory_item_id",
        "purchase_orders", ["inventory_item_id"],
    )
    op.create_index(
        "ix_purchase_orders_status", "purchase_orders", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_purchase_orders_status", table_name="purchase_orders")
    op.drop_index(
        "ix_purchase_orders_inventory_item_id", table_name="purchase_orders"
    )
    op.drop_table("purchase_orders")
    op.drop_index("ix_inventory_items_project_id", table_name="inventory_items")
    op.drop_table("inventory_items")
