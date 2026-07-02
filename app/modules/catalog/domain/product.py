"""Pure domain model. This file must not depend on FastAPI, SQLAlchemy, Redis, ChromaDB or Telegram."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.catalog.domain.enums import ProductCategory, ProductRestriction
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import ProductCode, ProductName


@dataclass()
class Product:
    code: ProductCode
    name: ProductName
    category: ProductCategory
    price: MoneyCOP
    is_active: bool = True
    is_available: bool = True
    restricted_to: ProductRestriction = ProductRestriction.NONE
    requires_age_verification: bool = False

    @property
    def can_be_listed(self) -> bool:
        return self.is_active

    @property
    def is_restricted(self) -> bool:
        return self.restricted_to != ProductRestriction.NONE or self.requires_age_verification

