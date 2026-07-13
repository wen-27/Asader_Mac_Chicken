"""SQLAlchemy ORM models for persistence. These classes are storage records, not domain entities."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.infrastructure.database.base import Base, TimestampMixin


class OrderORM(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("subtotal_cop >= 0", name="ck_orders_subtotal_cop_non_negative"),
        CheckConstraint("delivery_price_cop >= 0", name="ck_orders_delivery_price_cop_non_negative"),
        CheckConstraint("total_cop >= 0", name="ck_orders_total_cop_non_negative"),
        UniqueConstraint("order_number", name="uq_orders_order_number"),
        Index("ix_orders_chat_id", "chat_id"),
        Index("ix_orders_order_number", "order_number"),
        Index("ix_orders_fulfillment_status_created_at", "fulfillment_type", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_number: Mapped[str] = mapped_column(String(80), nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    customer_name: Mapped[str] = mapped_column(String(180), nullable=False)
    phone: Mapped[str] = mapped_column(String(40), nullable=False)
    address: Mapped[str] = mapped_column(String(240), nullable=False)
    neighborhood: Mapped[str] = mapped_column(String(160), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(80), nullable=False)
    observations: Mapped[str] = mapped_column(String(500), default="Ninguna", nullable=False)
    subtotal_cop: Mapped[int] = mapped_column(Integer, nullable=False)
    delivery_price_cop: Mapped[int] = mapped_column(Integer, nullable=False)
    total_cop: Mapped[int] = mapped_column(Integer, nullable=False)
    fulfillment_type: Mapped[str] = mapped_column(String(20), default="DELIVERY", nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    payment_proof_received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_proof_reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    printed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    items: Mapped[list["OrderItemORM"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class OrderItemORM(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint("unit_price_cop >= 0", name="ck_order_items_unit_price_cop_non_negative"),
        CheckConstraint("subtotal_cop >= 0", name="ck_order_items_subtotal_cop_non_negative"),
        Index("ix_order_items_order_id", "order_id"),
        Index("ix_order_items_product_code", "product_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_code: Mapped[str] = mapped_column(String(80), nullable=False)
    product_name: Mapped[str] = mapped_column(String(180), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_cop: Mapped[int] = mapped_column(Integer, nullable=False)
    subtotal_cop: Mapped[int] = mapped_column(Integer, nullable=False)

    order: Mapped[OrderORM] = relationship(back_populates="items")
