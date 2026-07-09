"""SQLAlchemy ORM models for persistence. These classes are storage records, not domain entities."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database.base import Base, TimestampMixin


class TelegramSessionORM(TimestampMixin, Base):
    __tablename__ = "telegram_sessions"
    __table_args__ = (
        UniqueConstraint("chat_id", name="uq_telegram_sessions_chat_id"),
        Index("ix_telegram_sessions_chat_id", "chat_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    current_step: Mapped[str] = mapped_column(String(80), nullable=False)
    selected_product_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    selected_chicken_part: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    cart_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"),
        default=list,
        nullable=False,
    )
    customer_name: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(240), nullable=True)
    neighborhood: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    payment_method: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    observations: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
