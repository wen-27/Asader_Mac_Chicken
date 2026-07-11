"""add message media fields

Revision ID: 20260711_0006
Revises: 20260710_0005
Create Date: 2026-07-11 09:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260711_0006"
down_revision: str | None = "20260710_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("telegram_messages", sa.Column("media_id", sa.String(length=180), nullable=True))
    op.add_column("telegram_messages", sa.Column("media_type", sa.String(length=40), nullable=True))
    op.add_column("telegram_messages", sa.Column("media_mime_type", sa.String(length=120), nullable=True))
    op.add_column("telegram_messages", sa.Column("media_sha256", sa.String(length=160), nullable=True))


def downgrade() -> None:
    op.drop_column("telegram_messages", "media_sha256")
    op.drop_column("telegram_messages", "media_mime_type")
    op.drop_column("telegram_messages", "media_type")
    op.drop_column("telegram_messages", "media_id")
