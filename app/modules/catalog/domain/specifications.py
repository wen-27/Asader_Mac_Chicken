"""Pure domain model. This file must not depend on FastAPI, SQLAlchemy, Redis, ChromaDB or Telegram."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from app.modules.catalog.domain.enums import ProductRestriction
from app.modules.catalog.domain.product import Product


@dataclass(frozen=True)
class AgeRestrictedProductSpecification:
    def is_satisfied_by(self, product: Product) -> bool:
        return product.requires_age_verification


@dataclass(frozen=True)
class ProductAvailabilitySpecification:
    is_holiday: Callable[[date], bool]

    def is_satisfied_by(self, product: Product, business_date: date) -> bool:
        if not product.is_active or not product.is_available:
            return False
        if product.restricted_to == ProductRestriction.WEEKEND_OR_HOLIDAY:
            return business_date.weekday() in (5, 6) or self.is_holiday(business_date)
        return True

