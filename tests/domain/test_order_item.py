"""Pure domain model. This file must not depend on FastAPI, SQLAlchemy, Redis, ChromaDB or Telegram."""

from __future__ import annotations

from dataclasses import replace

from app.modules.catalog.domain.enums import ProductCategory
from app.modules.catalog.domain.product import Product
from app.modules.orders.domain.order_item import OrderItem
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import ProductCode, ProductName


def test_order_item_keeps_price_snapshot() -> None:
    product = Product(
        code=ProductCode("BROASTER_MEDIO"),
        name=ProductName("1/2 Broasted"),
        category=ProductCategory.POLLO_BROASTER,
        price=MoneyCOP(25500),
    )

    item = OrderItem.from_product(product, quantity=2)
    changed_product = replace(product, price=MoneyCOP(30000))

    assert changed_product.price == MoneyCOP(30000)
    assert item.unit_price_snapshot == MoneyCOP(25500)
    assert item.subtotal_snapshot == MoneyCOP(51000)

