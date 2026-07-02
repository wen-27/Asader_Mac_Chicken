"""SQLAlchemy repository adapter. Keep queries here and business rules in domain/application code."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.orders.domain.order import Order
from app.modules.orders.infrastructure.mappers import order_from_orm, order_to_orm
from app.modules.orders.infrastructure.models import OrderORM
from app.shared.domain.value_object import ChatId, OrderId


class SqlAlchemyOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_order_number(self, order_number: OrderId) -> Order | None:
        result = await self.session.execute(
            select(OrderORM)
            .options(selectinload(OrderORM.items))
            .where(OrderORM.order_number == order_number.value)
        )
        row = result.scalar_one_or_none()
        return order_from_orm(row) if row else None

    async def list_by_chat_id(self, chat_id: ChatId, limit: int = 20) -> list[Order]:
        result = await self.session.execute(
            select(OrderORM)
            .options(selectinload(OrderORM.items))
            .where(OrderORM.chat_id == chat_id.value)
            .order_by(OrderORM.created_at.desc())
            .limit(limit)
        )
        return [order_from_orm(row) for row in result.scalars().all()]

    async def add(self, order: Order, chat_id: ChatId) -> Order:
        row = order_to_orm(order, chat_id.value)
        self.session.add(row)
        await self.session.flush()
        return order_from_orm(row)

    async def save(self, order: Order) -> Order:
        result = await self.session.execute(
            select(OrderORM)
            .options(selectinload(OrderORM.items))
            .where(OrderORM.order_number == order.order_id.value)
        )
        row = result.scalar_one()
        row.status = order.status.value
        await self.session.flush()
        return order_from_orm(row)
