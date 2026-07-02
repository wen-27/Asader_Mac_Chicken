"""add admin order workflow fields

Revision ID: 20260701_0003
Revises: 20260701_0002
Create Date: 2026-07-01 00:03:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260701_0003"
down_revision: str | None = "20260701_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("printed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("rejection_reason", sa.String(length=500), nullable=True))
    op.create_index("ix_orders_status_created_at", "orders", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_orders_status_created_at", table_name="orders")
    op.drop_column("orders", "rejection_reason")
    op.drop_column("orders", "printed_at")
    op.drop_column("orders", "rejected_at")
    op.drop_column("orders", "accepted_at")
