"""Pure domain model. This file must not depend on FastAPI, SQLAlchemy, Redis, ChromaDB or Telegram."""

from __future__ import annotations

from dataclasses import dataclass

from app.shared.domain.exceptions import InvalidValueError
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import ProductCode, ProductName


@dataclass(frozen=True)
class CartItem:
    product_code: ProductCode
    product_name: ProductName
    unit_price: MoneyCOP
    quantity: int

    def __post_init__(self) -> None:
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise InvalidValueError("cart item quantity must be an integer")
        if self.quantity <= 0:
            raise InvalidValueError("cart item quantity must be greater than zero")

    @property
    def subtotal(self) -> MoneyCOP:
        return self.unit_price * self.quantity

