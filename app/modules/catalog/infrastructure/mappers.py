"""Mapping helpers between pure domain objects and infrastructure/ORM records."""

from __future__ import annotations

from app.modules.catalog.domain.enums import ProductCategory, ProductRestriction
from app.modules.catalog.domain.product import Product
from app.modules.catalog.domain.product_alias import ProductAlias, normalize_alias
from app.modules.catalog.infrastructure.models import ProductAliasORM, ProductORM
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import ProductCode, ProductName


def product_to_orm(product: Product) -> ProductORM:
    return ProductORM(
        code=product.code.value,
        name=product.name.value,
        category=product.category.value,
        price_cop=product.price.amount,
        is_active=product.is_active,
        is_available=product.is_available,
        restricted_to=product.restricted_to.value,
        requires_age_verification=product.requires_age_verification,
    )


def product_from_orm(row: ProductORM) -> Product:
    return Product(
        code=ProductCode(row.code),
        name=ProductName(row.name),
        category=ProductCategory(row.category),
        price=MoneyCOP(row.price_cop),
        is_active=row.is_active,
        is_available=row.is_available,
        restricted_to=ProductRestriction(row.restricted_to),
        requires_age_verification=row.requires_age_verification,
    )


def alias_to_orm(alias: ProductAlias, product_id: int) -> ProductAliasORM:
    return ProductAliasORM(
        product_id=product_id,
        alias=alias.alias,
        normalized_alias=normalize_alias(alias.alias),
    )


def alias_from_orm(row: ProductAliasORM) -> ProductAlias:
    return ProductAlias(
        product_code=ProductCode(row.product.code),
        alias=row.normalized_alias,
    )
