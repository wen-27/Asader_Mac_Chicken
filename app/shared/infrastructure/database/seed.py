"""Coordinates idempotent seeders that load reference data required by the bot."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.modules.admin.infrastructure.seeders.admin_user_seeder import (
    AdminUserSeedResult,
    seed_admin_user,
)
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
    admin_user: AdminUserSeedResult
    catalog: CatalogSeedResult
    delivery_zones: DeliveryZoneSeedResult


async def seed_database(session: AsyncSession) -> SeedResult:
    admin_user_result = await seed_admin_user(session, get_settings())
    catalog_result = await seed_catalog(session)
    delivery_result = await seed_delivery_zones(session)
    return SeedResult(
        admin_user=admin_user_result,
        catalog=catalog_result,
        delivery_zones=delivery_result,
    )
