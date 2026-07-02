"""Cart use case that empties the current Telegram session cart."""

from __future__ import annotations

from app.modules.cart.application.use_cases.results import CartOperationStatus, CartResult
from app.modules.conversations.application.ports import TelegramSessionRepository
from app.modules.conversations.domain.conversation_state import ConversationState
from app.shared.domain.value_object import ChatId


class ClearCart:
    def __init__(self, sessions: TelegramSessionRepository) -> None:
        self._sessions = sessions

    async def execute(self, chat_id: int) -> CartResult:
        session = await self._sessions.get_by_chat_id(ChatId(chat_id))
        if session is None:
            return CartResult(CartOperationStatus.EMPTY_CART, tuple(), 0)
        session.empty_cart()
        session.clear_selected_product()
        session.move_to(ConversationState.MAIN_MENU)
        await self._sessions.save(session)
        return CartResult(CartOperationStatus.OK, tuple(), 0)

