"""Redis-backed read model/cache adapter. Data here must be rebuildable from PostgreSQL."""

from __future__ import annotations

import json

from app.modules.catalog.application.ports import ProductRepository
from app.modules.catalog.domain.enums import ProductCategory, ProductRestriction
from app.modules.catalog.domain.product import Product
from app.shared.application.redis_ports import RedisCachePort
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import ProductCode, ProductName


class CachedProductRepository:
    LIST_ACTIVE_KEY = "catalog:products:active"

    def __init__(
        self,
        wrapped: ProductRepository,
        cache: RedisCachePort,
        ttl_seconds: int = 300,
    ) -> None:
        self._wrapped = wrapped
        self._cache = cache
        self._ttl_seconds = ttl_seconds

    async def get_by_code(self, code: ProductCode) -> Product | None:
        products = await self.list_active()
        for product in products:
            if product.code == code:
                return product
        return await self._wrapped.get_by_code(code)

    async def list_active(self) -> list[Product]:
        cached = await self._cache.get_text(self.LIST_ACTIVE_KEY)
        if cached:
            return [_product_from_dict(item) for item in json.loads(cached)]
        products = await self._wrapped.list_active()
        await self._cache.set_text(
            self.LIST_ACTIVE_KEY,
            json.dumps([_product_to_dict(product) for product in products]),
            self._ttl_seconds,
        )
        return products

    async def add(self, product: Product) -> Product:
        saved = await self._wrapped.add(product)
        await self._cache.delete(self.LIST_ACTIVE_KEY)
        return saved


def _product_to_dict(product: Product) -> dict[str, object]:
    return {
        "code": product.code.value,
        "name": product.name.value,
        "category": product.category.value,
        "price_cop": product.price.amount,
        "is_active": product.is_active,
        "is_available": product.is_available,
        "restricted_to": product.restricted_to.value,
        "requires_age_verification": product.requires_age_verification,
    }


def _product_from_dict(data: dict[str, object]) -> Product:
    return Product(
        code=ProductCode(str(data["code"])),
        name=ProductName(str(data["name"])),
        category=ProductCategory(str(data["category"])),
        price=MoneyCOP(int(data["price_cop"])),
        is_active=bool(data["is_active"]),
        is_available=bool(data["is_available"]),
        restricted_to=ProductRestriction(str(data["restricted_to"])),
        requires_age_verification=bool(data["requires_age_verification"]),
    )

