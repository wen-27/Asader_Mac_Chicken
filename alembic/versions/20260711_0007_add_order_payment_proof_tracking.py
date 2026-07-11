"""add order payment proof tracking

Revision ID: 20260711_0007
Revises: 20260711_0006
Create Date: 2026-07-11 10:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260711_0007"
down_revision: str | None = "20260711_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("payment_proof_received_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("payment_proof_reminder_sent_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "payment_proof_reminder_sent_at")
    op.drop_column("orders", "payment_proof_received_at")
