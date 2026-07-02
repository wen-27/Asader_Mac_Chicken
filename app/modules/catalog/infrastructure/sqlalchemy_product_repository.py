"""SQLAlchemy repository adapter. Keep queries here and business rules in domain/application code."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.catalog.domain.product import Product
from app.modules.catalog.domain.product_alias import ProductAlias, normalize_alias
from app.modules.catalog.infrastructure.mappers import (
    alias_from_orm,
    alias_to_orm,
    product_from_orm,
    product_to_orm,
)
from app.modules.catalog.infrastructure.models import ProductAliasORM, ProductORM
from app.shared.domain.value_object import ProductCode


class SqlAlchemyProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_code(self, code: ProductCode) -> Product | None:
        result = await self.session.execute(
            select(ProductORM).where(ProductORM.code == code.value)
        )
        row = result.scalar_one_or_none()
        return product_from_orm(row) if row else None

    async def list_active(self) -> list[Product]:
        result = await self.session.execute(
            select(ProductORM).where(ProductORM.is_active.is_(True)).order_by(ProductORM.id)
        )
        return [product_from_orm(row) for row in result.scalars().all()]

    async def add(self, product: Product) -> Product:
        row = product_to_orm(product)
        self.session.add(row)
        await self.session.flush()
        return product_from_orm(row)


class SqlAlchemyProductAliasRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_alias(self, normalized_alias: str) -> ProductAlias | None:
        result = await self.session.execute(
            select(ProductAliasORM)
            .options(selectinload(ProductAliasORM.product))
            .where(ProductAliasORM.normalized_alias == normalize_alias(normalized_alias))
        )
        row = result.scalar_one_or_none()
        return alias_from_orm(row) if row else None

    async def list_by_product_code(self, code: ProductCode) -> list[ProductAlias]:
        result = await self.session.execute(
            select(ProductAliasORM)
            .join(ProductAliasORM.product)
            .options(selectinload(ProductAliasORM.product))
            .where(ProductORM.code == code.value)
            .order_by(ProductAliasORM.id)
        )
        return [alias_from_orm(row) for row in result.scalars().all()]

    async def add(self, alias: ProductAlias) -> ProductAlias:
        result = await self.session.execute(
            select(ProductORM).where(ProductORM.code == alias.product_code.value)
        )
        product_row = result.scalar_one()
        row = alias_to_orm(alias, product_row.id)
        self.session.add(row)
        await self.session.flush()
        row.product = product_row
        return alias_from_orm(row)

