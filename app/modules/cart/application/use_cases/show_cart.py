"""Cart read use case that formats current cart totals from integer COP values."""

from __future__ import annotations

from app.modules.cart.application.use_cases.results import CartOperationStatus, CartResult
from app.modules.conversations.application.ports import TelegramSessionRepository
from app.shared.domain.value_object import ChatId


class ShowCart:
    def __init__(self, sessions: TelegramSessionRepository) -> None:
        self._sessions = sessions

    async def execute(self, chat_id: int) -> CartResult:
        session = await self._sessions.get_by_chat_id(ChatId(chat_id))
        if session is None or not session.cart:
            return CartResult(CartOperationStatus.EMPTY_CART, tuple(), 0)
        return CartResult(CartOperationStatus.OK, tuple(session.cart), session.cart_total.amount)

