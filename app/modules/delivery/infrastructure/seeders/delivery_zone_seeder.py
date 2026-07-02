"""Idempotent delivery-zone seeder. Keep normalized neighborhoods aligned with lookup behavior."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.domain.product_alias import normalize_alias
from app.modules.delivery.infrastructure.models import DeliveryZoneORM
from app.modules.delivery.infrastructure.seeders.delivery_zone_data import DELIVERY_ZONE_SEEDS


@dataclass(frozen=True)
class DeliveryZoneSeedResult:
    zones_upserted: int


async def seed_delivery_zones(session: AsyncSession) -> DeliveryZoneSeedResult:
    upserted = 0
    for seed in DELIVERY_ZONE_SEEDS:
        normalized_neighborhood = normalize_alias(seed.neighborhood)
        result = await session.execute(
            select(DeliveryZoneORM).where(DeliveryZoneORM.code == seed.code)
        )
        row = result.scalar_one_or_none()
        if row is None:
            session.add(
                DeliveryZoneORM(
                    code=seed.code,
                    neighborhood=seed.neighborhood,
                    normalized_neighborhood=normalized_neighborhood,
                    delivery_price_cop=seed.delivery_price_cop,
                    is_active=seed.is_active,
                )
            )
        else:
            row.neighborhood = seed.neighborhood
            row.normalized_neighborhood = normalized_neighborhood
            row.delivery_price_cop = seed.delivery_price_cop
            row.is_active = seed.is_active
        upserted += 1
    await session.flush()
    return DeliveryZoneSeedResult(zones_upserted=upserted)

