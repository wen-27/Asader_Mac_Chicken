"""SQLAlchemy adapter for operational stock controls."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.application.stock_controls import StockControl
from app.modules.catalog.infrastructure.models import StockControlORM


class SqlAlchemyStockControlRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_controls(self) -> list[StockControl]:
        result = await self.session.execute(select(StockControlORM).order_by(StockControlORM.id))
        return [_stock_control_from_orm(row) for row in result.scalars().all()]

    async def set_available(self, code: str, is_available: bool) -> StockControl | None:
        result = await self.session.execute(select(StockControlORM).where(StockControlORM.code == code))
        row = result.scalar_one_or_none()
        if row is None:
            return None
        row.is_available = is_available
        row.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return _stock_control_from_orm(row)


def _stock_control_from_orm(row: StockControlORM) -> StockControl:
    return StockControl(
        code=row.code,
        label=row.label,
        group_label=row.group_label,
        product_code=row.product_code,
        variant_label=row.variant_label,
        is_available=row.is_available,
    )
