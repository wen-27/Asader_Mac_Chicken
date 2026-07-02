"""Delivery-price use cases for manual zones and map-based fallback.

The restaurant has a trusted manual price table. Those zones always win. The
OpenRouteService distance estimate is only used when the customer writes a
human neighborhood/address that does not match a known manual zone.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional

from app.modules.delivery.application.ports import DeliveryDistancePort, DeliveryZoneRepository
from app.modules.delivery.domain.delivery_zone import DeliveryZone
from app.modules.catalog.domain.product_alias import normalize_alias
from app.shared.domain.value_object import Neighborhood


@dataclass(frozen=True)
class CalculateDeliveryResult:
    found: bool
    delivery_price_cop: int
    zone: DeliveryZone | None = None
    distance_km: float | None = None
    pricing_source: str = "zone"


@dataclass(frozen=True)
class DeliveryPricingConfig:
    origin_address: str
    base_price_cop: int = 2000
    price_per_km_cop: int = 2000
    round_to_cop: int = 500


class CalculateDelivery:
    def __init__(self, delivery_zones: DeliveryZoneRepository) -> None:
        self._delivery_zones = delivery_zones

    async def execute(self, neighborhood: str) -> CalculateDeliveryResult:
        # Simple zone lookup used by older flows and tests. Keep this behavior
        # exact because manual prices are the business source for known barrios.
        zone = await self._delivery_zones.get_by_neighborhood(Neighborhood(neighborhood))
        if zone is None:
            return CalculateDeliveryResult(found=False, delivery_price_cop=0)
        return CalculateDeliveryResult(
            found=True,
            delivery_price_cop=zone.delivery_price.amount,
            zone=zone,
        )


class CalculateMapBasedDelivery:
    def __init__(
        self,
        delivery_zones: DeliveryZoneRepository,
        distance_client: Optional[DeliveryDistancePort],
        config: DeliveryPricingConfig,
    ) -> None:
        self._delivery_zones = delivery_zones
        self._distance_client = distance_client
        self._config = config

    async def execute(
        self,
        address: str,
        neighborhood: str,
    ) -> CalculateDeliveryResult:
        # Manual table first: Lagos/Manantial/Provenza/etc. should not depend on
        # external APIs, quota, geocoding quality or network availability.
        zone = await _find_manual_zone(self._delivery_zones, neighborhood)
        if zone is not None:
            return CalculateDeliveryResult(
                found=True,
                delivery_price_cop=zone.delivery_price.amount,
                zone=zone,
                distance_km=0 if _is_base_delivery_neighborhood(neighborhood) else None,
                pricing_source="zone",
            )
        destination = _destination_text(address, neighborhood)
        if self._distance_client is not None and destination:
            try:
                distance_km = await self._distance_client.driving_distance_km(
                    self._config.origin_address,
                    destination,
                )
                return CalculateDeliveryResult(
                    found=True,
                    delivery_price_cop=_price_from_distance(distance_km, self._config),
                    distance_km=distance_km,
                    pricing_source="openrouteservice",
                )
            except Exception:
                # Delivery must keep moving even when ORS is down. The fallback
                # below protects checkout while avoiding a too-low 2000 COP fee.
                pass

        return CalculateDeliveryResult(
            found=False,
            delivery_price_cop=max(self._config.base_price_cop, 4000),
            pricing_source="fallback_minimum",
        )


def _destination_text(address: str, neighborhood: str) -> str:
    municipality = _municipality_for_neighborhood(neighborhood)
    parts = [
        part.strip()
        for part in [address, neighborhood, f"{municipality}, Santander, Colombia"]
        if part.strip()
    ]
    return ", ".join(parts)


def _price_from_distance(distance_km: float, config: DeliveryPricingConfig) -> int:
    # Bands are calibrated to stay close to the original paper/manual delivery
    # table. Do not replace them with a naive per-km formula without checking
    # Lagos 2, Manantial, Cacique, Cabecera and HIC examples.
    calibrated_bands = [
        (2.5, 4000),
        (4.5, 6000),
        (6.5, 8000),
        (8.8, 10000),
        (11.0, 12000),
    ]
    for max_km, price_cop in calibrated_bands:
        if distance_km <= max_km:
            return max(config.base_price_cop, price_cop)

    extra_distance = distance_km - calibrated_bands[-1][0]
    extra_price = int(math.ceil(extra_distance * config.price_per_km_cop))
    raw_price = calibrated_bands[-1][1] + extra_price
    return int(math.ceil(raw_price / config.round_to_cop) * config.round_to_cop)


def _is_base_delivery_neighborhood(neighborhood: str) -> bool:
    normalized = normalize_alias(neighborhood)
    return normalized in {
        "lagos 2",
        "lagos ii",
        "lagos dos",
        "santa coloma",
        "lagos 2 santa coloma",
        "lagos ii santa coloma",
    }


async def _find_manual_zone(
    delivery_zones: DeliveryZoneRepository,
    neighborhood: str,
) -> Optional[DeliveryZone]:
    # Customers rarely type the exact seed name. Compare normalized full names,
    # slash-separated aliases and partial inclusions such as "Manantial".
    exact = await delivery_zones.get_by_neighborhood(Neighborhood(neighborhood))
    if exact is not None:
        return exact
    normalized = normalize_alias(neighborhood)
    if not normalized:
        return None
    for zone in await delivery_zones.list_active():
        if zone.code == "DOMICILIO_ADICIONAL":
            continue
        zone_normalized = normalize_alias(zone.neighborhood.value)
        zone_parts = [
            normalize_alias(part)
            for part in zone.neighborhood.value.replace(",", "/").split("/")
            if normalize_alias(part)
        ]
        if normalized == zone_normalized:
            return zone
        if normalized in zone_parts:
            return zone
        if any(part in normalized or normalized in part for part in zone_parts):
            return zone
    return None


def _municipality_for_neighborhood(neighborhood: str) -> str:
    normalized = normalize_alias(neighborhood)
    if any(
        name in normalized
        for name in [
            "lagos",
            "santa coloma",
            "bucarica",
            "bellavista",
            "canaveral",
            "florida",
        ]
    ):
        return "Floridablanca"
    if "hospital internacional" in normalized or normalized == "hic":
        return "Piedecuesta"
    return "Bucaramanga"
