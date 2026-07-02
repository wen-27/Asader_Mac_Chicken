"""Mapping helpers between pure domain objects and infrastructure/ORM records."""

from __future__ import annotations

from app.modules.telegram.domain.telegram_message import TelegramMessage
from app.modules.telegram.infrastructure.models import TelegramMessageORM
from app.shared.domain.value_object import ChatId


def message_to_orm(message: TelegramMessage, direction: str) -> TelegramMessageORM:
    return TelegramMessageORM(
        update_id=message.update_id,
        chat_id=message.chat_id.value,
        direction=direction,
        message_text=message.text_raw,
        normalized_message_text=message.text_normalized,
        message_type="text",
        telegram_message_id=message.message_id,
        created_at=message.received_at,
    )


def message_from_orm(row: TelegramMessageORM) -> TelegramMessage:
    return TelegramMessage(
        chat_id=ChatId(row.chat_id),
        message_id=row.telegram_message_id,
        update_id=row.update_id or 0,
        text_raw=row.message_text,
        text_normalized=row.normalized_message_text,
        received_at=row.created_at,
    )
