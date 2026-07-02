"""Application use case. It coordinates domain rules through ports and should stay framework-agnostic."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.modules.cart.domain.cart_item import CartItem


class CartOperationStatus(str, Enum):
    OK = "OK"
    EMPTY_CART = "EMPTY_CART"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
    PRODUCT_RESTRICTED = "PRODUCT_RESTRICTED"


@dataclass(frozen=True)
class CartResult:
    status: CartOperationStatus
    items: tuple[CartItem, ...]
    total_cop: int
    added_item: CartItem | None = None
    removed_item: CartItem | None = None

