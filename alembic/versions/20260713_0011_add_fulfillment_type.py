"""Add order fulfillment type to bot sessions and local orders.

Revision ID: 20260713_0011
Revises: 20260712_0010
Create Date: 2026-07-13 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260713_0011"
down_revision: str | None = "20260712_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "telegram_sessions",
        sa.Column("fulfillment_type", sa.String(length=20), nullable=False, server_default="DELIVERY"),
    )
    op.add_column(
        "orders",
        sa.Column("fulfillment_type", sa.String(length=20), nullable=False, server_default="DELIVERY"),
    )
    op.create_index("ix_orders_fulfillment_status_created_at", "orders", ["fulfillment_type", "status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_orders_fulfillment_status_created_at", table_name="orders")
    op.drop_column("orders", "fulfillment_type")
    op.drop_column("telegram_sessions", "fulfillment_type")
