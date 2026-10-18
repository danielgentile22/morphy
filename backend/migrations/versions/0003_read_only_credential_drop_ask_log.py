"""Read-only credentials; drop the retired Ask Claude log (ADR-077).

Adds ``credential.read_only`` (not null, default false, so every existing
credential keeps full write access) for the public demo's read-only
principal, and drops the ``ask_log`` table: the Ask Claude route and its
only client (the data-audit site) are gone.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ask_log", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ask_log_tenant_id"))
        batch_op.drop_index("ix_ask_log_tenant_created")
    op.drop_table("ask_log")

    with op.batch_alter_table("credential", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("read_only", sa.Boolean(), server_default=sa.false(), nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("credential", schema=None) as batch_op:
        batch_op.drop_column("read_only")

    # Restores the 0002 shape (empty: the logged Q&A rows are not recoverable).
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
