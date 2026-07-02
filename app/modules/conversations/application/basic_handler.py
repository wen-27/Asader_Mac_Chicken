"""Conversation orchestration code. It should coordinate state transitions and delegate business work to use cases/services."""

from __future__ import annotations

from app.shared.domain.value_object import ChatId


class BasicConversationMessageHandler:
    async def handle(self, message_text: str, chat_id: ChatId) -> str:
        return "Mensaje recibido. El flujo conversacional se conectará en la siguiente fase."

