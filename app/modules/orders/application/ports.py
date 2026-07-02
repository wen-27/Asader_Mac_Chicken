"""Application port definitions. These protocols keep use cases independent from database, Redis, Telegram and API clients."""

from __future__ import annotations

from typing import Protocol

from app.modules.orders.domain.order import Order
from app.shared.domain.value_object import ChatId, OrderId


class OrderRepository(Protocol):
    async def get_by_order_number(self, order_number: OrderId) -> Order | None:
        ...

    async def list_by_chat_id(self, chat_id: ChatId, limit: int = 20) -> list[Order]:
        ...

    async def add(self, order: Order, chat_id: ChatId) -> Order:
        ...

    async def save(self, order: Order) -> Order:
        ...
