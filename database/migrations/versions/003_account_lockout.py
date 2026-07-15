"""Add account lockout columns to users — Sprint 8 security hardening

Revision ID: 003
Revises: 002
Create Date: 2026-07-15

Adds three new columns to the existing users table:
    failed_login_attempts  INT NOT NULL DEFAULT 0
    locked_until            TIMESTAMPTZ NULL
    last_failed_login_at    TIMESTAMPTZ NULL

No existing column is modified or dropped. See
database/models/company.py User model and docs/DECISIONS.md for the
full account-lockout design rationale.

Upgrade:   Adds the three columns with a safe default for existing rows.
Downgrade: Drops the three columns.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "failed_login_attempts", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "users", sa.Column("locked_until", sa.TIMESTAMP(timezone=True), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("last_failed_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "last_failed_login_at")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
