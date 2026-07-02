"""SQLAlchemy implementation of the Unit of Work contract with async transaction boundaries."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.catalog.infrastructure.sqlalchemy_product_repository import (
    SqlAlchemyProductAliasRepository,
    SqlAlchemyProductRepository,
)
from app.modules.conversations.infrastructure.sqlalchemy_session_repository import (
    SqlAlchemyTelegramSessionRepository,
)
from app.modules.customers.infrastructure.sqlalchemy_customer_repository import (
    SqlAlchemyCustomerRepository,
)
from app.modules.delivery.infrastructure.sqlalchemy_delivery_zone_repository import (
    SqlAlchemyDeliveryZoneRepository,
)
from app.modules.orders.infrastructure.sqlalchemy_order_repository import SqlAlchemyOrderRepository
from app.modules.telegram.infrastructure.sqlalchemy_message_repository import (
    SqlAlchemyTelegramMessageRepository,
)
from app.shared.infrastructure.database.session import AsyncSessionFactory


class SqlAlchemyUnitOfWork:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] = AsyncSessionFactory,
    ) -> None:
        self.session_factory = session_factory

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = self.session_factory()
        self.products = SqlAlchemyProductRepository(self.session)
        self.product_aliases = SqlAlchemyProductAliasRepository(self.session)
        self.telegram_messages = SqlAlchemyTelegramMessageRepository(self.session)
        self.telegram_sessions = SqlAlchemyTelegramSessionRepository(self.session)
        self.customers = SqlAlchemyCustomerRepository(self.session)
        self.delivery_zones = SqlAlchemyDeliveryZoneRepository(self.session)
        self.orders = SqlAlchemyOrderRepository(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            await self.rollback()
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
