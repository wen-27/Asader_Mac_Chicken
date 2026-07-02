"""Pure domain model. This file must not depend on FastAPI, SQLAlchemy, Redis, ChromaDB or Telegram."""

from __future__ import annotations

from dataclasses import dataclass

from app.shared.domain.value_object import Address, CustomerName, Neighborhood, PhoneNumber


@dataclass()
class Customer:
    name: CustomerName
    phone: PhoneNumber
    address: Address
    neighborhood: Neighborhood
    observations: str = "Ninguna"

