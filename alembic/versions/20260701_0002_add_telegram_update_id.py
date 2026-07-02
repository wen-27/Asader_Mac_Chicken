"""Alembic migration file. It evolves the PostgreSQL schema and must stay reversible where practical."""

from __future__ import annotations

"""add telegram update id

Revision ID: 20260701_0002
Revises: 20260701_0001
Create Date: 2026-07-01 00:02:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260701_0002"
down_revision: str | None = "20260701_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("telegram_messages", sa.Column("update_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "telegram_messages",
        sa.Column("normalized_message_text", sa.Text(), server_default="", nullable=False),
    )
    op.create_index("ix_telegram_messages_update_id", "telegram_messages", ["update_id"])
    op.create_index(
        "uq_telegram_messages_inbound_update_id",
        "telegram_messages",
        ["update_id"],
        unique=True,
        postgresql_where=sa.text("direction = 'inbound' AND update_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_telegram_messages_inbound_update_id", table_name="telegram_messages")
    op.drop_index("ix_telegram_messages_update_id", table_name="telegram_messages")
    op.drop_column("telegram_messages", "normalized_message_text")
    op.drop_column("telegram_messages", "update_id")
