"""Pure domain model. This file must not depend on FastAPI, SQLAlchemy, Redis, ChromaDB or Telegram."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.shared.domain.value_object import ChatId


@dataclass(frozen=True)
class TelegramMessage:
    chat_id: ChatId
    message_id: int
    update_id: int
    text_raw: str
    text_normalized: str
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
