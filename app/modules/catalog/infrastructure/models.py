"""SQLAlchemy ORM models for persistence. These classes are storage records, not domain entities."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.infrastructure.database.base import Base, TimestampMixin


class ProductORM(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price_cop >= 0", name="ck_products_price_cop_non_negative"),
        UniqueConstraint("code", name="uq_products_code"),
        Index("ix_products_code", "code"),
        Index("ix_products_category", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    price_cop: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    restricted_to: Mapped[str] = mapped_column(String(80), default="NONE", nullable=False)
    requires_age_verification: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    aliases: Mapped[list["ProductAliasORM"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )


class ProductAliasORM(Base):
    __tablename__ = "product_aliases"
    __table_args__ = (
        UniqueConstraint("normalized_alias", name="uq_product_aliases_normalized_alias"),
        Index("ix_product_aliases_product_id", "product_id"),
        Index("ix_product_aliases_normalized_alias", "normalized_alias"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    alias: Mapped[str] = mapped_column(String(180), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(180), nullable=False)

    product: Mapped[ProductORM] = relationship(back_populates="aliases")


class StockControlORM(TimestampMixin, Base):
    __tablename__ = "stock_controls"
    __table_args__ = (
        UniqueConstraint("code", name="uq_stock_controls_code"),
        Index("ix_stock_controls_code", "code"),
        Index("ix_stock_controls_product_code", "product_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(180), nullable=False)
    group_label: Mapped[str] = mapped_column(String(80), nullable=False)
    product_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    variant_label: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
