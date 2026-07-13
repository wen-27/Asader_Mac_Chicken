"""Add operational stock controls.

Revision ID: 20260712_0009
Revises: 20260711_0008
Create Date: 2026-07-12 21:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260712_0009"
down_revision: str | None = "20260711_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DEFAULT_CONTROLS: tuple[tuple[str, str, str, str | None, str | None, bool], ...] = (
    ("ASADO_FAMILY", "Pollo asado", "Pollo asado", None, None, True),
    ("SOPA_ADICIONAL", "Sopa adicional", "Adicionales", "SOPA_ADICIONAL", None, True),
    ("MADURO_QUESO", "Maduro con queso", "Especiales fin de semana", "MADURO_QUESO", None, True),
    ("LASAGNA_MIXTA", "Lasagna mixta", "Especiales fin de semana", "LASAGNA_MIXTA", None, True),
    ("ASADO_CUARTO_PIERNA", "1/4 asado - pierna", "Presas asadas", "ASADO_CUARTO", "Pierna", True),
    ("ASADO_CUARTO_PECHUGA", "1/4 asado - pechuga", "Presas asadas", "ASADO_CUARTO", "Pechuga", True),
    ("BROASTER_CUARTO_PIERNA", "1/4 broaster - pierna", "Presas broaster", "BROASTER_CUARTO", "Pierna", True),
    ("BROASTER_CUARTO_PECHUGA", "1/4 broaster - pechuga", "Presas broaster", "BROASTER_CUARTO", "Pechuga", True),
    (
        "ASADO_34_2PIERNAS_1PECHUGA",
        "3/4 asado - 2 piernas y 1 pechuga",
        "Presas asadas",
        "ASADO_34",
        "2 piernas y 1 pechuga",
        True,
    ),
    (
        "ASADO_34_2PECHUGAS_1PIERNA",
        "3/4 asado - 2 pechugas y 1 pierna",
        "Presas asadas",
        "ASADO_34",
        "2 pechugas y 1 pierna",
        True,
    ),
    (
        "BROASTER_34_2PIERNAS_1PECHUGA",
        "3/4 broaster - 2 piernas y 1 pechuga",
        "Presas broaster",
        "BROASTER_34",
        "2 piernas y 1 pechuga",
        True,
    ),
    (
        "BROASTER_34_2PECHUGAS_1PIERNA",
        "3/4 broaster - 2 pechugas y 1 pierna",
        "Presas broaster",
        "BROASTER_34",
        "2 pechugas y 1 pierna",
        True,
    ),
)


def upgrade() -> None:
    op.create_table(
        "stock_controls",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=180), nullable=False),
        sa.Column("group_label", sa.String(length=80), nullable=False),
        sa.Column("product_code", sa.String(length=80), nullable=True),
        sa.Column("variant_label", sa.String(length=80), nullable=True),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_stock_controls_code"),
    )
    op.create_index("ix_stock_controls_code", "stock_controls", ["code"], unique=False)
    op.create_index("ix_stock_controls_product_code", "stock_controls", ["product_code"], unique=False)

    stock_controls = sa.table(
        "stock_controls",
        sa.column("code", sa.String),
        sa.column("label", sa.String),
        sa.column("group_label", sa.String),
        sa.column("product_code", sa.String),
        sa.column("variant_label", sa.String),
        sa.column("is_available", sa.Boolean),
    )
    op.bulk_insert(
        stock_controls,
        [
            {
                "code": code,
                "label": label,
                "group_label": group_label,
                "product_code": product_code,
                "variant_label": variant_label,
                "is_available": is_available,
            }
            for code, label, group_label, product_code, variant_label, is_available in DEFAULT_CONTROLS
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_stock_controls_product_code", table_name="stock_controls")
    op.drop_index("ix_stock_controls_code", table_name="stock_controls")
    op.drop_table("stock_controls")
