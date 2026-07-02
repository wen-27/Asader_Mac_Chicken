"""Pure domain model. This file must not depend on FastAPI, SQLAlchemy, Redis, ChromaDB or Telegram."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.cart.domain.cart_item import CartItem
from app.modules.catalog.domain.product import Product
from app.shared.domain.exceptions import InvalidValueError
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import ProductCode, ProductName


@dataclass(frozen=True)
class OrderItem:
    product_code: ProductCode
    product_name: ProductName
    unit_price_snapshot: MoneyCOP
    quantity: int
    subtotal_snapshot: MoneyCOP

    def __post_init__(self) -> None:
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise InvalidValueError("order item quantity must be an integer")
        if self.quantity <= 0:
            raise InvalidValueError("order item quantity must be greater than zero")
        expected_subtotal = self.unit_price_snapshot * self.quantity
        if expected_subtotal != self.subtotal_snapshot:
            raise InvalidValueError("order item subtotal snapshot is inconsistent")

    @classmethod
    def from_product(cls, product: Product, quantity: int) -> "OrderItem":
        return cls(
            product_code=product.code,
            product_name=product.name,
            unit_price_snapshot=MoneyCOP(product.price.amount),
            quantity=quantity,
            subtotal_snapshot=product.price * quantity,
        )

    @classmethod
    def from_cart_item(cls, item: CartItem) -> "OrderItem":
        return cls(
            product_code=item.product_code,
            product_name=item.product_name,
            unit_price_snapshot=MoneyCOP(item.unit_price.amount),
            quantity=item.quantity,
            subtotal_snapshot=item.subtotal,
        )

