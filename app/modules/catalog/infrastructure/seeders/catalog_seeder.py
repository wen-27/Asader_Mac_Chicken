"""Idempotent catalog seeder. Running it multiple times should update records without duplicating them."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.domain.product_alias import normalize_alias
from app.modules.catalog.infrastructure.models import ProductAliasORM, ProductORM
from app.modules.catalog.infrastructure.seeders.catalog_data import (
    PRODUCT_ALIAS_SEEDS,
    PRODUCT_SEEDS,
)


@dataclass(frozen=True)
class CatalogSeedResult:
    products_upserted: int
    aliases_upserted: int


async def seed_products(session: AsyncSession) -> int:
    upserted = 0
    for seed in PRODUCT_SEEDS:
        result = await session.execute(select(ProductORM).where(ProductORM.code == seed.code))
        row = result.scalar_one_or_none()
        if row is None:
            session.add(
                ProductORM(
                    code=seed.code,
                    name=seed.name,
                    category=seed.category.value,
                    price_cop=seed.price_cop,
                    is_active=seed.is_active,
                    is_available=seed.is_available,
                    restricted_to=seed.restricted_to.value,
                    requires_age_verification=seed.requires_age_verification,
                )
            )
        else:
            row.name = seed.name
            row.category = seed.category.value
            row.price_cop = seed.price_cop
            row.is_active = seed.is_active
            row.is_available = seed.is_available
            row.restricted_to = seed.restricted_to.value
            row.requires_age_verification = seed.requires_age_verification
        upserted += 1
    await session.flush()
    return upserted


async def seed_product_aliases(session: AsyncSession) -> int:
    product_rows = await session.execute(select(ProductORM))
    products_by_code = {row.code: row for row in product_rows.scalars().all()}
    expected_aliases = {
        normalize_alias(alias)
        for seed in PRODUCT_ALIAS_SEEDS
        for alias in seed.aliases
    }
    upserted = 0

    for seed in PRODUCT_ALIAS_SEEDS:
        product = products_by_code[seed.product_code]
        for alias in seed.aliases:
            normalized_alias = normalize_alias(alias)
            result = await session.execute(
                select(ProductAliasORM).where(
                    ProductAliasORM.normalized_alias == normalized_alias
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                session.add(
                    ProductAliasORM(
                        product_id=product.id,
                        alias=alias,
                        normalized_alias=normalized_alias,
                    )
                )
            else:
                row.product_id = product.id
                row.alias = alias
                row.normalized_alias = normalized_alias
            upserted += 1
    await session.execute(
        delete(ProductAliasORM).where(ProductAliasORM.normalized_alias.not_in(expected_aliases))
    )
    await session.flush()
    return upserted


async def seed_catalog(session: AsyncSession) -> CatalogSeedResult:
    products_upserted = await seed_products(session)
    aliases_upserted = await seed_product_aliases(session)
    return CatalogSeedResult(
        products_upserted=products_upserted,
        aliases_upserted=aliases_upserted,
    )
