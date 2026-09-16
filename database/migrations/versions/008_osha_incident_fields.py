"""Add OSHA 300/301 classification fields to log_safety_incidents — Sprint 15

Revision ID: 008
Revises: 007
Create Date: 2026-09-16

Adds 7 nullable columns to the existing log_safety_incidents table
(ADR-061): osha_classification, injury_illness_type,
days_away_from_work_count, days_of_job_transfer_or_restriction_count,
case_number, worker_id (FK to workers, ondelete=SET NULL), and
worker_match_status.

No new tables, no existing column changed or dropped. worker_id is
nullable and ON DELETE SET NULL -- a deleted Worker must not cascade
into deleting safety-incident history, which is exactly the kind of
record OSHA compliance requires to survive independently of workforce
roster changes.

Upgrade:   Adds the 7 columns and the worker_id index to
           log_safety_incidents.
Downgrade: Drops the worker_id index and all 7 columns.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "log_safety_incidents",
        sa.Column("osha_classification", sa.String(30), nullable=True),
    )
    op.add_column(
        "log_safety_incidents",
        sa.Column("injury_illness_type", sa.String(30), nullable=True),
    )
    op.add_column(
        "log_safety_incidents",
        sa.Column("days_away_from_work_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "log_safety_incidents",
        sa.Column(
            "days_of_job_transfer_or_restriction_count", sa.Integer(), nullable=True
        ),
    )
    op.add_column(
        "log_safety_incidents",
        sa.Column("case_number", sa.String(50), nullable=True),
    )
    op.add_column(
        "log_safety_incidents",
        sa.Column(
            "worker_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.add_column(
        "log_safety_incidents",
        sa.Column("worker_match_status", sa.String(20), nullable=True),
    )
    op.create_foreign_key(
        "fk_log_safety_incidents_worker_id",
        "log_safety_incidents", "workers",
        ["worker_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_log_safety_incidents_worker_id", "log_safety_incidents", ["worker_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_log_safety_incidents_worker_id", table_name="log_safety_incidents"
    )
    op.drop_constraint(
        "fk_log_safety_incidents_worker_id", "log_safety_incidents", type_="foreignkey"
    )
    op.drop_column("log_safety_incidents", "worker_match_status")
    op.drop_column("log_safety_incidents", "worker_id")
    op.drop_column("log_safety_incidents", "case_number")
    op.drop_column(
        "log_safety_incidents", "days_of_job_transfer_or_restriction_count"
    )
    op.drop_column("log_safety_incidents", "days_away_from_work_count")
    op.drop_column("log_safety_incidents", "injury_illness_type")
    op.drop_column("log_safety_incidents", "osha_classification")
