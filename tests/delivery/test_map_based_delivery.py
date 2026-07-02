"""Automated test module. It documents expected behavior and protects production bot flows from regressions."""

from __future__ import annotations

import pytest

from app.modules.delivery.application.use_cases.calculate_delivery import (
    CalculateMapBasedDelivery,
    DeliveryPricingConfig,
)
from app.modules.delivery.domain.delivery_zone import DeliveryZone
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import Neighborhood


class FakeDeliveryZones:
    async def get_by_neighborhood(self, neighborhood: Neighborhood):
        if neighborhood.value.lower() == "provenza / diamante":
            return DeliveryZone(
                code="DOMICILIO_PROVENZA_DIAMANTE",
                neighborhood=neighborhood,
                delivery_price=MoneyCOP(7000),
            )
        return None

    async def list_active(self):
        return [
            DeliveryZone(
                code="DOMICILIO_LAGOS_2_SANTA_COLOMA",
                neighborhood=Neighborhood("Lagos 2 / Santa Coloma"),
                delivery_price=MoneyCOP(2000),
            ),
            DeliveryZone(
                code="DOMICILIO_PROVENZA_DIAMANTE",
                neighborhood=Neighborhood("Provenza / Diamante"),
                delivery_price=MoneyCOP(7000),
            ),
            DeliveryZone(
                code="DOMICILIO_EL_MANANTIAL",
                neighborhood=Neighborhood("El Manantial"),
                delivery_price=MoneyCOP(4000),
            ),
        ]

    async def add(self, zone):
        return zone


class FakeDistanceClient:
    async def driving_distance_km(self, origin: str, destination: str) -> float:
        return 2.4


class ShortDistanceClient:
    async def driving_distance_km(self, origin: str, destination: str) -> float:
        return 0.8


class FailingDistanceClient:
    async def driving_distance_km(self, origin: str, destination: str) -> float:
        raise RuntimeError("maps unavailable")


@pytest.mark.asyncio
async def test_map_delivery_uses_manual_zone_price_before_distance() -> None:
    use_case = CalculateMapBasedDelivery(
        FakeDeliveryZones(),
        FakeDistanceClient(),
        DeliveryPricingConfig(
            origin_address="Lagos 2",
            base_price_cop=2000,
            price_per_km_cop=2000,
            round_to_cop=500,
        ),
    )

    result = await use_case.execute("Calle 105", "Provenza")

    assert result.found is True
    assert result.delivery_price_cop == 7000
    assert result.pricing_source == "zone"


@pytest.mark.asyncio
async def test_map_delivery_matches_partial_manual_zone_names() -> None:
    use_case = CalculateMapBasedDelivery(
        FakeDeliveryZones(),
        FakeDistanceClient(),
        DeliveryPricingConfig(origin_address="Lagos 2"),
    )

    provenza = await use_case.execute("", "Provenza")
    diamante = await use_case.execute("", "Diamante")

    assert provenza.delivery_price_cop == 7000
    assert diamante.delivery_price_cop == 7000
    assert provenza.pricing_source == "zone"
    assert diamante.pricing_source == "zone"


@pytest.mark.asyncio
async def test_map_delivery_matches_el_manantial_manual_price() -> None:
    use_case = CalculateMapBasedDelivery(
        FakeDeliveryZones(),
        FakeDistanceClient(),
        DeliveryPricingConfig(origin_address="Lagos 2"),
    )

    result = await use_case.execute("Cra 28 a #195-33", "el manantial")

    assert result.delivery_price_cop == 4000
    assert result.pricing_source == "zone"


@pytest.mark.asyncio
async def test_map_delivery_uses_distance_for_unknown_neighborhood() -> None:
    use_case = CalculateMapBasedDelivery(
        FakeDeliveryZones(),
        FakeDistanceClient(),
        DeliveryPricingConfig(
            origin_address="Lagos 2",
            base_price_cop=2000,
            price_per_km_cop=1000,
            round_to_cop=500,
        ),
    )

    result = await use_case.execute("Calle falsa 123", "Barrio Nuevo")

    assert result.found is True
    assert result.distance_km == 2.4
    assert result.delivery_price_cop == 4000
    assert result.pricing_source == "openrouteservice"


@pytest.mark.asyncio
async def test_map_delivery_automatic_minimum_is_four_thousand() -> None:
    use_case = CalculateMapBasedDelivery(
        FakeDeliveryZones(),
        ShortDistanceClient(),
        DeliveryPricingConfig(
            origin_address="Lagos 2",
            base_price_cop=2000,
            price_per_km_cop=1000,
            round_to_cop=500,
        ),
    )

    result = await use_case.execute("Direccion cercana", "Barrio no manual")

    assert result.found is True
    assert result.distance_km == 0.8
    assert result.delivery_price_cop == 4000
    assert result.pricing_source == "openrouteservice"


@pytest.mark.asyncio
async def test_map_delivery_fallback_minimum_is_four_thousand_for_unknown_zone() -> None:
    use_case = CalculateMapBasedDelivery(
        FakeDeliveryZones(),
        FailingDistanceClient(),
        DeliveryPricingConfig(
            origin_address="Lagos 2",
            base_price_cop=2000,
            price_per_km_cop=1000,
            round_to_cop=500,
        ),
    )

    result = await use_case.execute("Direccion sin mapa", "Barrio no manual")

    assert result.found is False
    assert result.delivery_price_cop == 4000
    assert result.pricing_source == "fallback_minimum"


@pytest.mark.asyncio
async def test_map_delivery_falls_back_to_zone_when_maps_fails() -> None:
    use_case = CalculateMapBasedDelivery(
        FakeDeliveryZones(),
        FailingDistanceClient(),
        DeliveryPricingConfig(origin_address="Lagos 2"),
    )

    result = await use_case.execute("Cualquier direccion", "Provenza")

    assert result.found is True
    assert result.delivery_price_cop == 7000
    assert result.pricing_source == "zone"


@pytest.mark.asyncio
async def test_map_delivery_keeps_lagos_2_base_price() -> None:
    use_case = CalculateMapBasedDelivery(
        FakeDeliveryZones(),
        FakeDistanceClient(),
        DeliveryPricingConfig(
            origin_address="Lagos 2",
            base_price_cop=2000,
            price_per_km_cop=1000,
            round_to_cop=500,
        ),
    )

    result = await use_case.execute("Cra 28a#195-33", "Lagos 2")

    assert result.delivery_price_cop == 2000
    assert result.pricing_source == "zone"
