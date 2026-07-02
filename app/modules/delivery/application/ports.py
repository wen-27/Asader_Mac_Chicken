"""Application port definitions. These protocols keep use cases independent from database, Redis, Telegram and API clients."""

from __future__ import annotations

from typing import Protocol

from app.modules.delivery.domain.delivery_zone import DeliveryZone
from app.shared.domain.value_object import Neighborhood


class DeliveryZoneRepository(Protocol):
    async def get_by_neighborhood(self, neighborhood: Neighborhood) -> DeliveryZone | None:
        ...

    async def list_active(self) -> list[DeliveryZone]:
        ...

    async def add(self, zone: DeliveryZone) -> DeliveryZone:
        ...


class DeliveryDistancePort(Protocol):
    async def driving_distance_km(self, origin: str, destination: str) -> float:
        ...
