"""Redis-backed read model/cache adapter. Data here must be rebuildable from PostgreSQL."""

from __future__ import annotations

import json

from app.modules.delivery.application.ports import DeliveryZoneRepository
from app.modules.delivery.domain.delivery_zone import DeliveryZone
from app.shared.application.redis_ports import RedisCachePort
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import Neighborhood
from app.shared.utils.text_normalizer import normalize_text


class CachedDeliveryZoneRepository:
    LIST_ACTIVE_KEY = "delivery:zones:active"

    def __init__(
        self,
        wrapped: DeliveryZoneRepository,
        cache: RedisCachePort,
        ttl_seconds: int = 900,
    ) -> None:
        self._wrapped = wrapped
        self._cache = cache
        self._ttl_seconds = ttl_seconds

    async def get_by_neighborhood(self, neighborhood: Neighborhood) -> DeliveryZone | None:
        zones = await self.list_active()
        normalized = normalize_text(neighborhood.value)
        for zone in zones:
            if normalize_text(zone.neighborhood.value) == normalized:
                return zone
        return await self._wrapped.get_by_neighborhood(neighborhood)

    async def list_active(self) -> list[DeliveryZone]:
        cached = await self._cache.get_text(self.LIST_ACTIVE_KEY)
        if cached:
            return [_zone_from_dict(item) for item in json.loads(cached)]
        zones = await self._wrapped.list_active()
        await self._cache.set_text(
            self.LIST_ACTIVE_KEY,
            json.dumps([_zone_to_dict(zone) for zone in zones]),
            self._ttl_seconds,
        )
        return zones

    async def add(self, zone: DeliveryZone) -> DeliveryZone:
        saved = await self._wrapped.add(zone)
        await self._cache.delete(self.LIST_ACTIVE_KEY)
        return saved


def _zone_to_dict(zone: DeliveryZone) -> dict[str, object]:
    return {
        "code": zone.code,
        "neighborhood": zone.neighborhood.value,
        "delivery_price_cop": zone.delivery_price.amount,
        "is_active": zone.is_active,
    }


def _zone_from_dict(data: dict[str, object]) -> DeliveryZone:
    return DeliveryZone(
        code=str(data["code"]),
        neighborhood=Neighborhood(str(data["neighborhood"])),
        delivery_price=MoneyCOP(int(data["delivery_price_cop"])),
        is_active=bool(data["is_active"]),
    )

