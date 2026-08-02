from __future__ import annotations

import pytest

from app.modules.conversations.application.ports import ConversationMessageHandler
from app.modules.telegram.application.handle_update.use_case import (
    HandleTelegramUpdateUseCase,
    TelegramInboundMessage,
)
from app.modules.telegram.domain.telegram_message import TelegramMessage
from app.shared.domain.value_object import ChatId


class FakeMessageRepository:
    def __init__(self) -> None:
        self.messages: list[tuple[str, TelegramMessage]] = []

    async def add(self, message: TelegramMessage, direction: str = "inbound") -> TelegramMessage:
        self.messages.append((direction, message))
        return message

    async def get_inbound_by_update_id(self, update_id: int) -> TelegramMessage | None:
        return None

    async def list_by_chat_id(self, chat_id: ChatId, limit: int = 50) -> list[TelegramMessage]:
        return []


class FakeTelegramClient:
    async def send_text_message(self, chat_id: ChatId, text: str) -> TelegramMessage:
        return TelegramMessage(
            chat_id=chat_id,
            message_id=999,
            update_id=0,
            text_raw=text,
            text_normalized=text,
        )


class FakeConversationHandler(ConversationMessageHandler):
    def __init__(self) -> None:
        self.last_message_text = ""

    async def handle(self, message_text: str, chat_id: ChatId) -> str:
        self.last_message_text = message_text
        return "ok"


@pytest.mark.asyncio
async def test_update_use_case_saves_original_but_handles_conversation_text() -> None:
    messages = FakeMessageRepository()
    handler = FakeConversationHandler()
    use_case = HandleTelegramUpdateUseCase(
        messages=messages,
        telegram_client=FakeTelegramClient(),
        conversation_handler=handler,
    )

    result = await use_case.execute(
        TelegramInboundMessage(
            update_id=1,
            message_id=2,
            chat_id=573022873946,
            text="quiero dos asador y un broster",
            conversation_text="quiero 2 pollos asados enteros y 1 pollo broaster entero",
            first_name=None,
            username=None,
            message_type="text",
        )
    )

    assert result.processed is True
    assert messages.messages[0][1].text_raw == "quiero dos asador y un broster"
    assert handler.last_message_text == "quiero 2 pollos asados enteros y 1 pollo broaster entero"


@pytest.mark.asyncio
async def test_update_use_case_sends_direct_clarification_without_handler() -> None:
    messages = FakeMessageRepository()
    handler = FakeConversationHandler()
    use_case = HandleTelegramUpdateUseCase(
        messages=messages,
        telegram_client=FakeTelegramClient(),
        conversation_handler=handler,
    )

    result = await use_case.execute(
        TelegramInboundMessage(
            update_id=1,
            message_id=2,
            chat_id=573022873946,
            text="una gasiosa roja",
            direct_response_text="Con gusto. Para no añadir una bebida equivocada, ¿deseas Coca-Cola, Kola o Colombiana?",
            first_name=None,
            username=None,
            message_type="text",
        )
    )

    assert result.response_text
    assert "bebida equivocada" in result.response_text
    assert handler.last_message_text == ""
