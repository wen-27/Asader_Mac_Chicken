"""Mapping helpers between pure domain objects and infrastructure/ORM records."""

from __future__ import annotations

from app.modules.customers.domain.customer import Customer
from app.modules.delivery.domain.delivery_zone import DeliveryZone
from app.modules.orders.domain.enums import OrderStatus, PaymentMethod
from app.modules.orders.domain.order import Order
from app.modules.orders.domain.order_item import OrderItem
from app.modules.orders.infrastructure.models import OrderItemORM, OrderORM
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import (
    Address,
    CustomerName,
    Neighborhood,
    OrderId,
    PhoneNumber,
    ProductCode,
    ProductName,
)


def order_item_to_orm(item: OrderItem) -> OrderItemORM:
    return OrderItemORM(
        product_code=item.product_code.value,
        product_name=item.product_name.value,
        quantity=item.quantity,
        unit_price_cop=item.unit_price_snapshot.amount,
        subtotal_cop=item.subtotal_snapshot.amount,
    )


def order_item_from_orm(row: OrderItemORM) -> OrderItem:
    return OrderItem(
        product_code=ProductCode(row.product_code),
        product_name=ProductName(row.product_name),
        quantity=row.quantity,
        unit_price_snapshot=MoneyCOP(row.unit_price_cop),
        subtotal_snapshot=MoneyCOP(row.subtotal_cop),
    )


def order_to_orm(order: Order, chat_id: int) -> OrderORM:
    return OrderORM(
        order_number=order.order_id.value,
        chat_id=chat_id,
        customer_name=order.customer.name.value,
        phone=order.customer.phone.value,
        address=order.customer.address.value,
        neighborhood=order.customer.neighborhood.value,
        payment_method=order.payment_method.value,
        observations=order.customer.observations,
        subtotal_cop=order.subtotal.amount,
        delivery_price_cop=order.delivery_zone.delivery_price.amount,
        total_cop=order.total.amount,
        status=order.status.value,
        items=[order_item_to_orm(item) for item in order.items],
    )


def order_from_orm(row: OrderORM) -> Order:
    customer = Customer(
        name=CustomerName(row.customer_name),
        phone=PhoneNumber(row.phone),
        address=Address(row.address),
        neighborhood=Neighborhood(row.neighborhood),
        observations=row.observations,
    )
    delivery_zone = DeliveryZone(
        code="ORDER_SNAPSHOT",
        neighborhood=Neighborhood(row.neighborhood),
        delivery_price=MoneyCOP(row.delivery_price_cop),
        is_active=True,
    )
    order = Order(
        order_id=OrderId(row.order_number),
        customer=customer,
        items=[order_item_from_orm(item) for item in row.items],
        delivery_zone=delivery_zone,
        payment_method=PaymentMethod(row.payment_method),
        status=OrderStatus(row.status),
    )
    return order

