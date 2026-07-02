"""Pure domain model. This file must not depend on FastAPI, SQLAlchemy, Redis, ChromaDB or Telegram."""

from __future__ import annotations

from dataclasses import dataclass

from app.shared.domain.exceptions import InvalidValueError


@dataclass(frozen=True)
class StringValueObject:
    value: str
    field_name: str = "value"

    def __post_init__(self) -> None:
        normalized = str(self.value).strip()
        if not normalized:
            raise InvalidValueError(f"{self.field_name} cannot be empty")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ProductCode:
    value: str

    def __post_init__(self) -> None:
        normalized = str(self.value).strip().upper().replace("-", "_").replace(" ", "_")
        if not normalized:
            raise InvalidValueError("product code cannot be empty")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ProductName(StringValueObject):
    field_name: str = "product name"


@dataclass(frozen=True)
class ChatId:
    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise InvalidValueError("chat id must be an integer")
        if self.value == 0:
            raise InvalidValueError("chat id cannot be zero")

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class PhoneNumber:
    value: str

    def __post_init__(self) -> None:
        digits = "".join(ch for ch in str(self.value) if ch.isdigit())
        if len(digits) < 7:
            raise InvalidValueError("phone number must have at least 7 digits")
        object.__setattr__(self, "value", digits)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class OrderId(StringValueObject):
    field_name: str = "order id"


@dataclass(frozen=True)
class CustomerName(StringValueObject):
    field_name: str = "customer name"


@dataclass(frozen=True)
class Address(StringValueObject):
    field_name: str = "address"


@dataclass(frozen=True)
class Neighborhood(StringValueObject):
    field_name: str = "neighborhood"

