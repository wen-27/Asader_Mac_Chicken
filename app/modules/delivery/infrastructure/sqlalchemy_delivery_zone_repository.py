"""SQLAlchemy repository adapter. Keep queries here and business rules in domain/application code."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.domain.product_alias import normalize_alias
from app.modules.delivery.domain.delivery_zone import DeliveryZone
from app.modules.delivery.infrastructure.mappers import zone_from_orm, zone_to_orm
from app.modules.delivery.infrastructure.models import DeliveryZoneORM
from app.shared.domain.value_object import Neighborhood


class SqlAlchemyDeliveryZoneRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_neighborhood(self, neighborhood: Neighborhood) -> DeliveryZone | None:
        result = await self.session.execute(
            select(DeliveryZoneORM).where(
                DeliveryZoneORM.normalized_neighborhood == normalize_alias(neighborhood.value),
                DeliveryZoneORM.is_active.is_(True),
            )
        )
        row = result.scalar_one_or_none()
        return zone_from_orm(row) if row else None

    async def list_active(self) -> list[DeliveryZone]:
        result = await self.session.execute(
            select(DeliveryZoneORM)
            .where(DeliveryZoneORM.is_active.is_(True))
            .order_by(DeliveryZoneORM.id)
        )
        return [zone_from_orm(row) for row in result.scalars().all()]

    async def add(self, zone: DeliveryZone) -> DeliveryZone:
        row = zone_to_orm(zone)
        self.session.add(row)
        await self.session.flush()
        return zone_from_orm(row)

