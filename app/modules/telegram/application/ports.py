"""Application port definitions. These protocols keep use cases independent from database, Redis, Telegram and API clients."""

from __future__ import annotations

from typing import Protocol

from app.modules.telegram.domain.telegram_message import TelegramMessage
from app.shared.domain.value_object import ChatId


class TelegramMessageRepository(Protocol):
    async def add(self, message: TelegramMessage, direction: str = "inbound") -> TelegramMessage:
        ...

    async def get_inbound_by_update_id(self, update_id: int) -> TelegramMessage | None:
        ...

    async def list_by_chat_id(self, chat_id: ChatId, limit: int = 50) -> list[TelegramMessage]:
        ...


class TelegramClient(Protocol):
    async def send_text_message(self, chat_id: ChatId, text: str) -> TelegramMessage:
        ...
