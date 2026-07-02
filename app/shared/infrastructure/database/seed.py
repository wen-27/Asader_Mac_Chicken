"""Coordinates idempotent seeders that load reference data required by the bot."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.infrastructure.seeders.catalog_seeder import (
    CatalogSeedResult,
    seed_catalog,
)
from app.modules.delivery.infrastructure.seeders.delivery_zone_seeder import (
    DeliveryZoneSeedResult,
    seed_delivery_zones,
)


@dataclass(frozen=True)
class SeedResult:
    catalog: CatalogSeedResult
    delivery_zones: DeliveryZoneSeedResult


async def seed_database(session: AsyncSession) -> SeedResult:
    catalog_result = await seed_catalog(session)
    delivery_result = await seed_delivery_zones(session)
    return SeedResult(catalog=catalog_result, delivery_zones=delivery_result)

