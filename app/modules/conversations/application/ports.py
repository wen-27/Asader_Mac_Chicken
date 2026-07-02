"""Application port definitions. These protocols keep use cases independent from database, Redis, Telegram and API clients."""

from __future__ import annotations

from typing import Protocol

from app.modules.conversations.domain.telegram_session import TelegramSession
from app.shared.domain.value_object import ChatId


class TelegramSessionRepository(Protocol):
    async def get_by_chat_id(self, chat_id: ChatId) -> TelegramSession | None:
        ...

    async def add(self, session: TelegramSession) -> TelegramSession:
        ...

    async def save(self, session: TelegramSession) -> TelegramSession:
        ...


class ConversationMessageHandler(Protocol):
    async def handle(self, message_text: str, chat_id: ChatId) -> str:
        ...
