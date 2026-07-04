"""Order confirmation use case. It finalizes the order workflow and clears session cart state."""

from __future__ import annotations

import logging

from app.config.settings import get_settings
from app.modules.conversations.application.ports import TelegramSessionRepository
from app.modules.orders.infrastructure.admin_backend_order_client import AdminBackendOrderClient
from app.modules.orders.application.ports import OrderRepository
from app.modules.orders.application.use_cases.results import CheckoutStatus, OrderResult
from app.shared.domain.value_object import ChatId, OrderId

logger = logging.getLogger(__name__)


class ConfirmOrder:
    def __init__(self, sessions: TelegramSessionRepository, orders: OrderRepository) -> None:
        self._sessions = sessions
        self._orders = orders

    async def execute(self, chat_id: int, order_number: str) -> OrderResult:
        order = await self._orders.get_by_order_number(OrderId(order_number))
        if order is None:
            return OrderResult(status=CheckoutStatus.ORDER_NOT_FOUND)
        order.confirm()
        order = await self._orders.save(order)
        session = await self._sessions.get_by_chat_id(ChatId(chat_id))
        if session is not None:
            session.empty_cart()
            session.clear_selected_product()
            await self._sessions.save(session)
        try:
            await AdminBackendOrderClient(get_settings()).sync_confirmed_order(order, chat_id)
        except Exception as exc:
            logger.exception("failed to sync confirmed order with admin backend: %s", exc)
        return OrderResult(status=CheckoutStatus.OK, order=order)
