"""Application use case. It coordinates domain rules through ports and should stay framework-agnostic."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.modules.orders.domain.order import Order


class CheckoutStatus(str, Enum):
    OK = "OK"
    EMPTY_CART = "EMPTY_CART"
    MISSING_CUSTOMER_DATA = "MISSING_CUSTOMER_DATA"
    DELIVERY_NOT_FOUND = "DELIVERY_NOT_FOUND"
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"


@dataclass(frozen=True)
class CheckoutSummary:
    status: CheckoutStatus
    subtotal_cop: int
    delivery_price_cop: int = 0
    total_cop: int = 0
    missing_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class OrderResult:
    status: CheckoutStatus
    order: Order | None = None
    missing_fields: tuple[str, ...] = ()

