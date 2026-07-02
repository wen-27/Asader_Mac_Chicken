"""Order creation use case. Confirmed order data is persisted in PostgreSQL with item price snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.conversations.application.ports import TelegramSessionRepository
from app.modules.customers.application.customer_data import CustomerData, missing_customer_fields
from app.modules.customers.domain.customer import Customer
from app.modules.delivery.application.ports import DeliveryZoneRepository
from app.modules.orders.application.order_number import generate_order_number
from app.modules.orders.application.ports import OrderRepository
from app.modules.orders.application.use_cases.results import CheckoutStatus, OrderResult
from app.modules.orders.domain.order import Order
from app.modules.orders.domain.order_item import OrderItem
from app.shared.domain.value_object import (
    Address,
    ChatId,
    CustomerName,
    Neighborhood,
    OrderId,
    PhoneNumber,
)


@dataclass(frozen=True)
class CreateOrderCommand:
    chat_id: int
    customer_data: CustomerData


class CreateOrder:
    def __init__(
        self,
        sessions: TelegramSessionRepository,
        delivery_zones: DeliveryZoneRepository,
        orders: OrderRepository,
    ) -> None:
        self._sessions = sessions
        self._delivery_zones = delivery_zones
        self._orders = orders

    async def execute(self, command: CreateOrderCommand) -> OrderResult:
        chat_id = ChatId(command.chat_id)
        session = await self._sessions.get_by_chat_id(chat_id)
        if session is None or not session.cart:
            return OrderResult(status=CheckoutStatus.EMPTY_CART)

        missing = missing_customer_fields(command.customer_data)
        if missing:
            return OrderResult(
                status=CheckoutStatus.MISSING_CUSTOMER_DATA,
                missing_fields=tuple(missing),
            )

        zone = await self._delivery_zones.get_by_neighborhood(
            Neighborhood(command.customer_data.neighborhood or "")
        )
        if zone is None:
            return OrderResult(status=CheckoutStatus.DELIVERY_NOT_FOUND)

        customer = Customer(
            name=CustomerName(command.customer_data.name or ""),
            phone=PhoneNumber(command.customer_data.phone or ""),
            address=Address(command.customer_data.address or ""),
            neighborhood=Neighborhood(command.customer_data.neighborhood or ""),
            observations=command.customer_data.observations or "Ninguna",
        )
        order = Order(
            order_id=OrderId(generate_order_number(command.chat_id)),
            customer=customer,
            items=[OrderItem.from_cart_item(item) for item in session.cart],
            delivery_zone=zone,
            payment_method=command.customer_data.payment_method,  # type: ignore[arg-type]
        )
        saved_order = await self._orders.add(order, chat_id)
        return OrderResult(status=CheckoutStatus.OK, order=saved_order)

