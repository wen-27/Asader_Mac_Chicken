"""Application port definitions. These protocols keep use cases independent from database, Redis, Telegram and API clients."""

from __future__ import annotations

from typing import Protocol

from app.modules.catalog.domain.product import Product
from app.modules.catalog.domain.product_alias import ProductAlias
from app.shared.domain.value_object import ProductCode


class ProductRepository(Protocol):
    async def get_by_code(self, code: ProductCode) -> Product | None:
        ...

    async def list_active(self) -> list[Product]:
        ...

    async def add(self, product: Product) -> Product:
        ...


class ProductAliasRepository(Protocol):
    async def get_by_alias(self, normalized_alias: str) -> ProductAlias | None:
        ...

    async def list_by_product_code(self, code: ProductCode) -> list[ProductAlias]:
        ...

    async def add(self, alias: ProductAlias) -> ProductAlias:
        ...

