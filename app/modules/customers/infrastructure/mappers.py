"""Mapping helpers between pure domain objects and infrastructure/ORM records."""

from __future__ import annotations

from app.modules.customers.domain.customer import Customer
from app.modules.customers.infrastructure.models import CustomerORM
from app.shared.domain.value_object import Address, CustomerName, Neighborhood, PhoneNumber


def customer_to_orm(customer: Customer, chat_id: int) -> CustomerORM:
    return CustomerORM(
        chat_id=chat_id,
        name=customer.name.value,
        phone=customer.phone.value,
        address=customer.address.value,
        neighborhood=customer.neighborhood.value,
    )


def customer_from_orm(row: CustomerORM) -> Customer:
    return Customer(
        name=CustomerName(row.name),
        phone=PhoneNumber(row.phone),
        address=Address(row.address),
        neighborhood=Neighborhood(row.neighborhood),
    )

