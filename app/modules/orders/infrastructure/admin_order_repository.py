"""SQLAlchemy read/write adapter for administrative order screens."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.orders.infrastructure.models import OrderORM


class SqlAlchemyAdminOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_statuses(
        self,
        statuses: Iterable[str],
        limit: int = 100,
    ) -> list[OrderORM]:
        result = await self._session.execute(
            select(OrderORM)
            .options(selectinload(OrderORM.items))
            .where(OrderORM.status.in_(list(statuses)))
            .order_by(OrderORM.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_id(self, order_id: int) -> OrderORM | None:
        result = await self._session.execute(
            select(OrderORM)
            .options(selectinload(OrderORM.items))
            .where(OrderORM.id == order_id)
        )
        return result.scalar_one_or_none()

    async def save(self, order: OrderORM) -> OrderORM:
        await self._session.flush()
        await self._session.refresh(order, attribute_names=["items"])
        return order

