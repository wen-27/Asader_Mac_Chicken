"""Application port definitions. These protocols keep use cases independent from database, Redis, Telegram and API clients."""

from __future__ import annotations

from typing import Protocol

from app.modules.customers.domain.customer import Customer
from app.shared.domain.value_object import ChatId


class CustomerRepository(Protocol):
    async def get_latest_by_chat_id(self, chat_id: ChatId) -> Customer | None:
        ...

    async def add(self, chat_id: ChatId, customer: Customer) -> Customer:
        ...

