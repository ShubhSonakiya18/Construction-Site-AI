"""Add log_change_orders table — Sprint 14

Revision ID: 007
Revises: 006
Create Date: 2026-09-16

Adds one new table:
    log_change_orders — one row per change order discussed or processed
        on a daily log, normalized out of
        DailyLog.client_communication.change_orders[] (which remains a
        JSON column for every other part of client_communication).

Why normalize just this one array out of an otherwise-JSON column: a
change order's `status` moves from pending_approval to approved or
rejected days or weeks after the log that first reported it — long
after that log has been approved and effectively frozen. A JSON array
on an approved DailyLog has nowhere to record that transition without
mutating an already-approved log's payload in place, which nothing
else in this codebase does. See database/models/log_items.py's
LogChangeOrder docstring and docs/DECISIONS.md.

No existing table is modified. DailyLog.client_communication keeps its
change_orders[] key in the persisted JSON as extracted — this
migration does not backfill or strip it; the normalized table is the
queryable source of truth going forward, and the JSON stays as the
verbatim record of what the extraction actually reported that day.

Upgrade:   Creates log_change_orders with its two indexes.
Downgrade: Drops log_change_orders.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "log_change_orders",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "daily_log_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("daily_logs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("change_order_id", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("estimated_cost_impact_usd", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "estimated_schedule_impact_days", sa.Numeric(6, 2), nullable=True
        ),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="pending_approval",
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
    )
    op.create_index(
        "ix_log_change_orders_daily_log_id",
        "log_change_orders", ["daily_log_id"],
    )
    op.create_index(
        "ix_log_change_orders_status", "log_change_orders", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_log_change_orders_status", table_name="log_change_orders")
    op.drop_index(
        "ix_log_change_orders_daily_log_id", table_name="log_change_orders"
    )
    op.drop_table("log_change_orders")
