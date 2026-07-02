"""SQLAlchemy ORM models for persistence. These classes are storage records, not domain entities."""

from __future__ import annotations

from app.modules.catalog.infrastructure.models import ProductAliasORM, ProductORM
from app.modules.conversations.infrastructure.models import TelegramSessionORM
from app.modules.customers.infrastructure.models import CustomerORM
from app.modules.delivery.infrastructure.models import DeliveryZoneORM
from app.modules.orders.infrastructure.models import OrderItemORM, OrderORM
from app.modules.telegram.infrastructure.models import TelegramMessageORM

__all__ = [
    "CustomerORM",
    "DeliveryZoneORM",
    "OrderItemORM",
    "OrderORM",
    "ProductAliasORM",
    "ProductORM",
    "TelegramMessageORM",
    "TelegramSessionORM",
]

