"""SQLAlchemy repository adapter. Keep queries here and business rules in domain/application code."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.domain.customer import Customer
from app.modules.customers.infrastructure.mappers import customer_from_orm, customer_to_orm
from app.modules.customers.infrastructure.models import CustomerORM
from app.shared.domain.value_object import ChatId


class SqlAlchemyCustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_latest_by_chat_id(self, chat_id: ChatId) -> Customer | None:
        result = await self.session.execute(
            select(CustomerORM)
            .where(CustomerORM.chat_id == chat_id.value)
            .order_by(CustomerORM.created_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return customer_from_orm(row) if row else None

    async def add(self, chat_id: ChatId, customer: Customer) -> Customer:
        row = customer_to_orm(customer, chat_id.value)
        self.session.add(row)
        await self.session.flush()
        return customer_from_orm(row)

