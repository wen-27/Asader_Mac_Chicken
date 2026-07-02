"""Pure domain model. This file must not depend on FastAPI, SQLAlchemy, Redis, ChromaDB or Telegram."""

from __future__ import annotations

from dataclasses import dataclass

from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import Neighborhood


@dataclass(frozen=True)
class DeliveryZone:
    code: str
    neighborhood: Neighborhood
    delivery_price: MoneyCOP
    is_active: bool = True

    def can_deliver(self) -> bool:
        return self.is_active

