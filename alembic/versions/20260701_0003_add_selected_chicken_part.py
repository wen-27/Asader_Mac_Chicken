"""Add selected chicken part to telegram sessions.

Revision ID: 20260701_0003
Revises: 20260701_0002
Create Date: 2026-07-05 18:58:00.000000
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
    op.add_column(
        "telegram_sessions",
        sa.Column("selected_chicken_part", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("telegram_sessions", "selected_chicken_part")
