"""Application-layer code. It defines use cases, DTOs and ports between domain and infrastructure."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.orders.domain.enums import PaymentMethod
from app.shared.utils.text_normalizer import normalize_text


@dataclass(frozen=True)
class CustomerData:
    name: str | None = None
    phone: str | None = None
    address: str | None = None
    neighborhood: str | None = None
    payment_method: PaymentMethod | None = None
    observations: str = "Ninguna"


PAYMENT_ALIASES: dict[str, PaymentMethod] = {
    "efectivo": PaymentMethod.CASH,
    "datáfono": PaymentMethod.DATAPHONE,
    "datafono": PaymentMethod.DATAPHONE,
    "nequi": PaymentMethod.NEQUI,
    "transferencia bancolombia": PaymentMethod.BANCOLOMBIA_TRANSFER,
    "transferencia": PaymentMethod.BANCOLOMBIA_TRANSFER,
    "bancolombia": PaymentMethod.BANCOLOMBIA_TRANSFER,
}


def parse_payment_method(value: str | None) -> PaymentMethod | None:
    if not value:
        return None
    return PAYMENT_ALIASES.get(normalize_text(value))


def missing_customer_fields(data: CustomerData) -> list[str]:
    missing: list[str] = []
    if not data.name:
        missing.append("nombre completo")
    if not data.phone:
        missing.append("teléfono")
    if not data.address:
        missing.append("dirección")
    if not data.neighborhood:
        missing.append("barrio")
    if data.payment_method is None:
        missing.append("método de pago")
    return missing

