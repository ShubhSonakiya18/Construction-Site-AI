"""Add project_alerts_sent table — Sprint 19

Revision ID: 009
Revises: 008
Create Date: 2026-09-17

Adds one new table:
    project_alerts_sent — one row per (project_id, alert_type), tracking
        the last time a real alert email was sent for that project and
        what computed status it was sent for. NOT an append-only audit
        log — a UniqueConstraint on (project_id, alert_type) means this
        is an upsert target, not a growing history.

Why this table exists: Sprint 14's budget_variance.status and Sprint 15's
safety_proactive_warnings are both real, correct, already-computed alert
conditions that were never pushed anywhere before Sprint 19 — both
sprints' own "Decided, not built" sections cited "no scheduler or
notification infrastructure" as the reason to stop at a computed field.
A periodic Celery Beat task checking these conditions needs a way to
avoid re-sending the identical alert every tick forever; see
docs/DECISIONS.md ADR-066 for why a per-(project, alert_type) last-sent
row was chosen over a pure previous-vs-current status diff.

Upgrade:   Creates project_alerts_sent with its unique constraint and index.
Downgrade: Drops project_alerts_sent.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_alerts_sent",
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
        sa.Column("alert_type", sa.String(30), nullable=False),
        sa.Column("last_status_value", sa.String(30), nullable=False),
        sa.Column("last_sent_at", sa.TIMESTAMP(timezone=True), nullable=False),
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
            "project_id", "alert_type", name="uq_project_alert_type"
        ),
    )
    op.create_index(
        "ix_project_alerts_sent_project_id",
        "project_alerts_sent", ["project_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_alerts_sent_project_id", table_name="project_alerts_sent"
    )
    op.drop_table("project_alerts_sent")
