"""Pure domain model. This file must not depend on FastAPI, SQLAlchemy, Redis, ChromaDB or Telegram."""

from __future__ import annotations

from datetime import date

from app.modules.catalog.domain.enums import ProductCategory, ProductRestriction
from app.modules.catalog.domain.product import Product
from app.modules.catalog.domain.specifications import (
    AgeRestrictedProductSpecification,
    ProductAvailabilitySpecification,
)
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import ProductCode, ProductName


def test_age_restricted_product_is_detected() -> None:
    product = Product(
        code=ProductCode("CERVEZA_LATA"),
        name=ProductName("Cerveza Lata"),
        category=ProductCategory.BEBIDAS_ALCOHOLICAS,
        price=MoneyCOP(4400),
        requires_age_verification=True,
    )

    assert AgeRestrictedProductSpecification().is_satisfied_by(product)


def test_weekend_or_holiday_product_is_unavailable_on_regular_weekday() -> None:
    product = Product(
        code=ProductCode("LASAGNA_MIXTA"),
        name=ProductName("Lasagna Mixta"),
        category=ProductCategory.ESPECIALES,
        price=MoneyCOP(20000),
        restricted_to=ProductRestriction.WEEKEND_OR_HOLIDAY,
    )
    spec = ProductAvailabilitySpecification(is_holiday=lambda _: False)

    assert not spec.is_satisfied_by(product, date(2026, 7, 1))


def test_weekend_or_holiday_product_is_available_on_weekend() -> None:
    product = Product(
        code=ProductCode("MADURO_QUESO"),
        name=ProductName("Maduro con Queso"),
        category=ProductCategory.ESPECIALES,
        price=MoneyCOP(9500),
        restricted_to=ProductRestriction.WEEKEND_OR_HOLIDAY,
    )
    spec = ProductAvailabilitySpecification(is_holiday=lambda _: False)

    assert spec.is_satisfied_by(product, date(2026, 7, 4))


def test_weekend_or_holiday_product_is_available_on_configured_holiday() -> None:
    product = Product(
        code=ProductCode("LASAGNA_MIXTA"),
        name=ProductName("Lasagna Mixta"),
        category=ProductCategory.ESPECIALES,
        price=MoneyCOP(20000),
        restricted_to=ProductRestriction.WEEKEND_OR_HOLIDAY,
    )
    spec = ProductAvailabilitySpecification(is_holiday=lambda value: value == date(2026, 7, 13))

    assert spec.is_satisfied_by(product, date(2026, 7, 13))
