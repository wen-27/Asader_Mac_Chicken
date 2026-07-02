"""Checkout use case that builds totals before customer confirmation."""

from __future__ import annotations

from app.modules.conversations.application.ports import TelegramSessionRepository
from app.modules.orders.application.use_cases.results import CheckoutStatus, CheckoutSummary
from app.shared.domain.value_object import ChatId


class PrepareCheckoutSummary:
    def __init__(self, sessions: TelegramSessionRepository) -> None:
        self._sessions = sessions

    async def execute(self, chat_id: int) -> CheckoutSummary:
        session = await self._sessions.get_by_chat_id(ChatId(chat_id))
        if session is None or not session.cart:
            return CheckoutSummary(status=CheckoutStatus.EMPTY_CART, subtotal_cop=0)
        return CheckoutSummary(
            status=CheckoutStatus.OK,
            subtotal_cop=session.cart_total.amount,
            total_cop=session.cart_total.amount,
        )

