"""Ask Claude Q&A log — the second migration (PRD #187 / slice 3 / #190).

Adds the tenant-scoped ``ask_log`` table that stores every completed catalog
Q&A with its context snapshot. The first revision after the ``0001`` baseline;
applies cleanly on a fresh DB and on the production database already stamped at
the baseline (the app runs upgrade-to-head at boot, PRD #134).

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ask_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=320), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("route", sa.String(length=200), nullable=False),
        sa.Column("selection", sa.Text(), nullable=True),
        sa.Column("signal_ids", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("ask_log", schema=None) as batch_op:
        batch_op.create_index(
            "ix_ask_log_tenant_created", ["tenant_id", "created_at", "id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_ask_log_tenant_id"), ["tenant_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("ask_log", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ask_log_tenant_id"))
        batch_op.drop_index("ix_ask_log_tenant_created")

    op.drop_table("ask_log")
