"""Application Unit of Work contract for transactional use cases."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol

from app.modules.catalog.application.ports import ProductAliasRepository, ProductRepository
from app.modules.conversations.application.ports import TelegramSessionRepository
from app.modules.customers.application.ports import CustomerRepository
from app.modules.delivery.application.ports import DeliveryZoneRepository
from app.modules.orders.application.ports import OrderRepository
from app.modules.telegram.application.ports import TelegramMessageRepository


class AsyncUnitOfWork(Protocol):
    products: ProductRepository
    product_aliases: ProductAliasRepository
    telegram_messages: TelegramMessageRepository
    telegram_sessions: TelegramSessionRepository
    customers: CustomerRepository
    delivery_zones: DeliveryZoneRepository
    orders: OrderRepository

    async def __aenter__(self) -> "AsyncUnitOfWork":
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        ...

    async def commit(self) -> None:
        ...

    async def rollback(self) -> None:
        ...
