"""Add scheduling tables — Sprint 11

Revision ID: 005
Revises: 004
Create Date: 2026-09-15

Adds two new tables:
    project_schedules — one row per project (unique on project_id; Sprint 11
        scope is exactly one active schedule per project, no revision
        history — see database/models/schedule.py module docstring).
    schedule_tasks     — one row per stage/task in a project's schedule,
        unique on (schedule_id, stage_id).

No existing table is modified. LogWorkItem.linked_schedule_task_id (added
in an earlier sprint's model, never in its own migration since it was a
plain unconstrained string column) is deliberately left as-is here — this
migration does not add a FK from it to schedule_tasks.id. See
database/models/schedule.py's module docstring for why the link stays
soft for now.

Upgrade:   Creates project_schedules and schedule_tasks with their indexes
           and unique constraints.
Downgrade: Drops schedule_tasks then project_schedules (child before
           parent, matching the FK direction).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_schedules",
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
        sa.Column("schedule_start_date", sa.Date(), nullable=False),
        sa.Column("critical_path_total_days", sa.Integer(), nullable=True),
        sa.Column("projected_completion_date", sa.Date(), nullable=True),
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
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("project_id", name="uq_project_schedules_project_id"),
    )

    op.create_table(
        "schedule_tasks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "schedule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("project_schedules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage_id", sa.String(100), nullable=False),
        sa.Column("stage_label", sa.String(200), nullable=False),
        sa.Column("sequence_order", sa.Integer(), nullable=False),
        sa.Column("planned_start_date", sa.Date(), nullable=False),
        sa.Column("planned_end_date", sa.Date(), nullable=False),
        sa.Column("planned_duration_days", sa.Integer(), nullable=False),
        sa.Column("actual_start_date", sa.Date(), nullable=True),
        sa.Column("actual_end_date", sa.Date(), nullable=True),
        sa.Column(
            "is_on_critical_path",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
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
        sa.UniqueConstraint(
            "schedule_id", "stage_id", name="uq_schedule_tasks_schedule_stage"
        ),
    )
    op.create_index(
        "ix_schedule_tasks_schedule_id", "schedule_tasks", ["schedule_id"]
    )
    op.create_index("ix_schedule_tasks_stage_id", "schedule_tasks", ["stage_id"])


def downgrade() -> None:
    op.drop_index("ix_schedule_tasks_stage_id", table_name="schedule_tasks")
    op.drop_index("ix_schedule_tasks_schedule_id", table_name="schedule_tasks")
    op.drop_table("schedule_tasks")
    op.drop_table("project_schedules")
