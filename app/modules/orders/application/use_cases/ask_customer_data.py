"""Checkout helper use case that asks for required delivery/customer fields."""

from __future__ import annotations

class AskCustomerData:
    def execute(self) -> tuple[str, ...]:
        return (
            "nombre completo",
            "teléfono",
            "dirección",
            "barrio",
            "método de pago",
            "observaciones",
        )

