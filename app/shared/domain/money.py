"""Pure domain model. This file must not depend on FastAPI, SQLAlchemy, Redis, ChromaDB or Telegram."""

from __future__ import annotations

from dataclasses import dataclass

from app.shared.domain.exceptions import InvalidValueError


@dataclass(frozen=True)
class MoneyCOP:
    amount: int

    def __post_init__(self) -> None:
        if isinstance(self.amount, bool) or not isinstance(self.amount, int):
            raise InvalidValueError("money amount must be an integer COP value")
        if self.amount < 0:
            raise InvalidValueError("money amount cannot be negative")

    def __add__(self, other: "MoneyCOP") -> "MoneyCOP":
        return MoneyCOP(self.amount + other.amount)

    def __mul__(self, quantity: int) -> "MoneyCOP":
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise InvalidValueError("quantity must be an integer")
        if quantity < 0:
            raise InvalidValueError("quantity cannot be negative")
        return MoneyCOP(self.amount * quantity)

    def __str__(self) -> str:
        return f"COP {self.amount}"

