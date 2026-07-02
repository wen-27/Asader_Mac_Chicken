"""Cart use case that removes the latest line while preserving remaining price snapshots."""

from __future__ import annotations

from app.modules.cart.application.use_cases.results import CartOperationStatus, CartResult
from app.modules.conversations.application.ports import TelegramSessionRepository
from app.shared.domain.value_object import ChatId


class RemoveLastCartItem:
    def __init__(self, sessions: TelegramSessionRepository) -> None:
        self._sessions = sessions

    async def execute(self, chat_id: int) -> CartResult:
        session = await self._sessions.get_by_chat_id(ChatId(chat_id))
        if session is None or not session.cart:
            return CartResult(CartOperationStatus.EMPTY_CART, tuple(), 0)
        removed = session.remove_last_cart_item()
        await self._sessions.save(session)
        return CartResult(
            status=CartOperationStatus.OK,
            items=tuple(session.cart),
            total_cop=session.cart_total.amount,
            removed_item=removed,
        )

