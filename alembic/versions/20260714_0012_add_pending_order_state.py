"""add pending order state

Revision ID: 20260714_0012
Revises: 20260713_0011
Create Date: 2026-07-14
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260714_0012"
down_revision = "20260713_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    json_type = sa.JSON()
    if bind.dialect.name == "postgresql":
        json_type = postgresql.JSONB()
    op.add_column("telegram_sessions", sa.Column("pending_order_json", json_type, nullable=True))


def downgrade() -> None:
    op.drop_column("telegram_sessions", "pending_order_json")
