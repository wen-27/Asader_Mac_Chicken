"""SQLAlchemy ORM models for persistence. These classes are storage records, not domain entities."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.database.base import Base


class TelegramMessageORM(Base):
    __tablename__ = "telegram_messages"
    __table_args__ = (
        Index("ix_telegram_messages_chat_id", "chat_id"),
        Index("ix_telegram_messages_update_id", "update_id"),
        Index("ix_telegram_messages_telegram_message_id", "telegram_message_id"),
        Index(
            "uq_telegram_messages_inbound_update_id",
            "update_id",
            unique=True,
            postgresql_where=text("direction = 'inbound' AND update_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    update_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_message_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    message_type: Mapped[str] = mapped_column(String(40), default="text", nullable=False)
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    media_id: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    media_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    media_mime_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    media_sha256: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
