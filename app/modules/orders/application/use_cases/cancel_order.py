"""Order cancellation use case for aborting checkout without creating a confirmed sale."""

from __future__ import annotations

from app.modules.conversations.application.ports import TelegramSessionRepository
from app.modules.conversations.domain.conversation_state import ConversationState
from app.shared.domain.value_object import ChatId


class CancelOrder:
    def __init__(self, sessions: TelegramSessionRepository) -> None:
        self._sessions = sessions

    async def execute(self, chat_id: int) -> None:
        session = await self._sessions.get_by_chat_id(ChatId(chat_id))
        if session is None:
            return
        session.empty_cart()
        session.clear_selected_product()
        session.move_to(ConversationState.MAIN_MENU)
        await self._sessions.save(session)

