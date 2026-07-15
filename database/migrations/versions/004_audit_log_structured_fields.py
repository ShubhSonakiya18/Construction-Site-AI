"""Add structured audit fields — Sprint 8 audit logging

Revision ID: 004
Revises: 003
Create Date: 2026-07-15

Adds five new columns to the existing audit_logs table:
    target_user_id  UUID NULL
    ip_address      VARCHAR(45) NULL
    user_agent      VARCHAR(500) NULL
    request_id      VARCHAR(64) NULL
    success         BOOLEAN NULL

No existing column is modified or dropped, and event_metadata is
untouched — it remains the free-form JSON field for event-specific
context that has no general cross-event meaning. See
database/models/generation.py AuditLog class docstring for the full
"why structured columns, why keep event_metadata too" rationale.

Upgrade:   Adds the five columns (all nullable — backward compatible
           with every existing audit_logs row, which has NULL in all
           five since they didn't exist yet) plus supporting indexes.
Downgrade: Drops the indexes and columns.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "audit_logs", sa.Column("ip_address", sa.String(45), nullable=True)
    )
    op.add_column(
        "audit_logs", sa.Column("user_agent", sa.String(500), nullable=True)
    )
    op.add_column(
        "audit_logs", sa.Column("request_id", sa.String(64), nullable=True)
    )
    op.add_column(
        "audit_logs", sa.Column("success", sa.Boolean(), nullable=True)
    )

    op.create_index("ix_audit_logs_target_user_id", "audit_logs", ["target_user_id"])
    op.create_index("ix_audit_logs_ip_address", "audit_logs", ["ip_address"])
    op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])
    op.create_index("ix_audit_logs_success", "audit_logs", ["success"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_success", table_name="audit_logs")
    op.drop_index("ix_audit_logs_request_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_ip_address", table_name="audit_logs")
    op.drop_index("ix_audit_logs_target_user_id", table_name="audit_logs")

    op.drop_column("audit_logs", "success")
    op.drop_column("audit_logs", "request_id")
    op.drop_column("audit_logs", "user_agent")
    op.drop_column("audit_logs", "ip_address")
    op.drop_column("audit_logs", "target_user_id")
