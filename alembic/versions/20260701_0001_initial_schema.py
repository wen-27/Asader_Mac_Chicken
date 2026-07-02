"""Alembic migration file. It evolves the PostgreSQL schema and must stay reversible where practical."""

from __future__ import annotations

"""initial schema

Revision ID: 20260701_0001
Revises:
Create Date: 2026-07-01 00:01:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260701_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("price_cop", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("restricted_to", sa.String(length=80), nullable=False),
        sa.Column("requires_age_verification", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("price_cop >= 0", name="ck_products_price_cop_non_negative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_products_code"),
    )
    op.create_index("ix_products_category", "products", ["category"], unique=False)
    op.create_index("ix_products_code", "products", ["code"], unique=False)

    op.create_table(
        "product_aliases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(length=180), nullable=False),
        sa.Column("normalized_alias", sa.String(length=180), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_alias", name="uq_product_aliases_normalized_alias"),
    )
    op.create_index("ix_product_aliases_normalized_alias", "product_aliases", ["normalized_alias"])
    op.create_index("ix_product_aliases_product_id", "product_aliases", ["product_id"])

    op.create_table(
        "telegram_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("message_type", sa.String(length=40), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_telegram_messages_chat_id", "telegram_messages", ["chat_id"])
    op.create_index(
        "ix_telegram_messages_telegram_message_id",
        "telegram_messages",
        ["telegram_message_id"],
    )

    op.create_table(
        "telegram_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("current_step", sa.String(length=80), nullable=False),
        sa.Column("selected_product_code", sa.String(length=80), nullable=True),
        sa.Column("cart_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("customer_name", sa.String(length=180), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("address", sa.String(length=240), nullable=True),
        sa.Column("neighborhood", sa.String(length=160), nullable=True),
        sa.Column("payment_method", sa.String(length=80), nullable=True),
        sa.Column("observations", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", name="uq_telegram_sessions_chat_id"),
    )
    op.create_index("ix_telegram_sessions_chat_id", "telegram_sessions", ["chat_id"])

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=False),
        sa.Column("address", sa.String(length=240), nullable=False),
        sa.Column("neighborhood", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customers_chat_id", "customers", ["chat_id"])
    op.create_index("ix_customers_phone", "customers", ["phone"])

    op.create_table(
        "delivery_zones",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("neighborhood", sa.String(length=160), nullable=False),
        sa.Column("normalized_neighborhood", sa.String(length=160), nullable=False),
        sa.Column("delivery_price_cop", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "delivery_price_cop >= 0",
            name="ck_delivery_zones_delivery_price_cop_non_negative",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_delivery_zones_code"),
        sa.UniqueConstraint(
            "normalized_neighborhood",
            name="uq_delivery_zones_normalized_neighborhood",
        ),
    )
    op.create_index("ix_delivery_zones_code", "delivery_zones", ["code"])
    op.create_index(
        "ix_delivery_zones_normalized_neighborhood",
        "delivery_zones",
        ["normalized_neighborhood"],
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_number", sa.String(length=80), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("customer_name", sa.String(length=180), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=False),
        sa.Column("address", sa.String(length=240), nullable=False),
        sa.Column("neighborhood", sa.String(length=160), nullable=False),
        sa.Column("payment_method", sa.String(length=80), nullable=False),
        sa.Column("observations", sa.String(length=500), nullable=False),
        sa.Column("subtotal_cop", sa.Integer(), nullable=False),
        sa.Column("delivery_price_cop", sa.Integer(), nullable=False),
        sa.Column("total_cop", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("subtotal_cop >= 0", name="ck_orders_subtotal_cop_non_negative"),
        sa.CheckConstraint(
            "delivery_price_cop >= 0",
            name="ck_orders_delivery_price_cop_non_negative",
        ),
        sa.CheckConstraint("total_cop >= 0", name="ck_orders_total_cop_non_negative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_number", name="uq_orders_order_number"),
    )
    op.create_index("ix_orders_chat_id", "orders", ["chat_id"])
    op.create_index("ix_orders_order_number", "orders", ["order_number"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("product_code", sa.String(length=80), nullable=False),
        sa.Column("product_name", sa.String(length=180), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_cop", sa.Integer(), nullable=False),
        sa.Column("subtotal_cop", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        sa.CheckConstraint(
            "unit_price_cop >= 0",
            name="ck_order_items_unit_price_cop_non_negative",
        ),
        sa.CheckConstraint(
            "subtotal_cop >= 0",
            name="ck_order_items_subtotal_cop_non_negative",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index("ix_order_items_product_code", "order_items", ["product_code"])


def downgrade() -> None:
    op.drop_index("ix_order_items_product_code", table_name="order_items")
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_index("ix_orders_order_number", table_name="orders")
    op.drop_index("ix_orders_chat_id", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_delivery_zones_normalized_neighborhood", table_name="delivery_zones")
    op.drop_index("ix_delivery_zones_code", table_name="delivery_zones")
    op.drop_table("delivery_zones")
    op.drop_index("ix_customers_phone", table_name="customers")
    op.drop_index("ix_customers_chat_id", table_name="customers")
    op.drop_table("customers")
    op.drop_index("ix_telegram_sessions_chat_id", table_name="telegram_sessions")
    op.drop_table("telegram_sessions")
    op.drop_index("ix_telegram_messages_telegram_message_id", table_name="telegram_messages")
    op.drop_index("ix_telegram_messages_chat_id", table_name="telegram_messages")
    op.drop_table("telegram_messages")
    op.drop_index("ix_product_aliases_product_id", table_name="product_aliases")
    op.drop_index("ix_product_aliases_normalized_alias", table_name="product_aliases")
    op.drop_table("product_aliases")
    op.drop_index("ix_products_code", table_name="products")
    op.drop_index("ix_products_category", table_name="products")
    op.drop_table("products")
