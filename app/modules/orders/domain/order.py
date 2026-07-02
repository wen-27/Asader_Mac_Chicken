"""Pure domain model. This file must not depend on FastAPI, SQLAlchemy, Redis, ChromaDB or Telegram."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.customers.domain.customer import Customer
from app.modules.delivery.domain.delivery_zone import DeliveryZone
from app.modules.orders.domain.enums import OrderStatus, PaymentMethod
from app.modules.orders.domain.order_item import OrderItem
from app.shared.domain.exceptions import BusinessRuleViolation
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import OrderId


@dataclass()
class Order:
    order_id: OrderId
    customer: Customer
    items: list[OrderItem]
    delivery_zone: DeliveryZone
    payment_method: PaymentMethod
    status: OrderStatus = OrderStatus.PENDING
    notes: str = ""
    _subtotal: MoneyCOP = field(init=False, repr=False)
    _total: MoneyCOP = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.items:
            raise BusinessRuleViolation("order must have at least one item")
        self._subtotal = self.calculate_subtotal()
        self._total = self._subtotal + self.delivery_zone.delivery_price

    @property
    def subtotal(self) -> MoneyCOP:
        return self._subtotal

    @property
    def total(self) -> MoneyCOP:
        return self._total

    def calculate_subtotal(self) -> MoneyCOP:
        subtotal = MoneyCOP(0)
        for item in self.items:
            subtotal += item.subtotal_snapshot
        return subtotal

    def confirm(self) -> None:
        if self.status == OrderStatus.CANCELLED:
            raise BusinessRuleViolation("cancelled orders cannot be confirmed")
        self.status = OrderStatus.CONFIRMED

    def cancel(self) -> None:
        if self.status == OrderStatus.CONFIRMED:
            raise BusinessRuleViolation("confirmed orders cannot be cancelled from domain")
        self.status = OrderStatus.CANCELLED

