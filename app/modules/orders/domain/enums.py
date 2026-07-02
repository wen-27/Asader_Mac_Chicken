"""Domain enums shared by entities and use cases. Add values carefully because persisted rows may depend on them."""

from __future__ import annotations

from enum import Enum


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class PaymentMethod(str, Enum):
    DATAPHONE = "Datáfono"
    NEQUI = "Nequi"
    BANCOLOMBIA_TRANSFER = "Transferencia Bancolombia"
    CASH = "Efectivo"
