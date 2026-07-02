"""Operator helper to compare OpenRouteService distances with the manual delivery-price table."""

from __future__ import annotations

import asyncio
from statistics import median

from app.config.settings import get_settings
from app.modules.delivery.application.use_cases.calculate_delivery import (
    DeliveryPricingConfig,
    _price_from_distance,
)
from app.modules.delivery.infrastructure.openrouteservice_distance_client import (
    OpenRouteServiceDistanceClient,
)
from app.shared.domain.exceptions import DomainError
from app.modules.delivery.infrastructure.seeders.delivery_zone_data import DELIVERY_ZONE_SEEDS


CALIBRATION_DESTINATIONS = {
    "DOMICILIO_BUCARICA_BELLAVISTA": "Bucarica, Floridablanca, Santander, Colombia",
    "DOMICILIO_CANAVERAL_FLORIDA": "Cañaveral, Floridablanca, Santander, Colombia",
    "DOMICILIO_PROVENZA_DIAMANTE": "Provenza, Bucaramanga, Santander, Colombia",
    "DOMICILIO_CACIQUE": "Centro Comercial Cacique, Bucaramanga, Santander, Colombia",
    "DOMICILIO_SAN_ANDRESITO": "San Andresito La Isla, Bucaramanga, Santander, Colombia",
    "DOMICILIO_CIUDADELA": "Ciudadela Real de Minas, Bucaramanga, Santander, Colombia",
    "DOMICILIO_CABECERA": "Cabecera del Llano, Bucaramanga, Santander, Colombia",
    "HOSPITAL_INTERNACIONAL": "Hospital Internacional de Colombia, Piedecuesta, Santander, Colombia",
}


async def main() -> None:
    settings = get_settings()
    try:
        client = OpenRouteServiceDistanceClient(settings)
    except DomainError as exc:
        print(f"No se pudo iniciar OpenRouteService: {exc}")
        print("Agrega OPENROUTESERVICE_API_KEY en .env.")
        return
    config = DeliveryPricingConfig(
        origin_address=settings.delivery_origin_address,
        base_price_cop=settings.delivery_base_price_cop,
        price_per_km_cop=settings.delivery_price_per_km_cop,
        round_to_cop=settings.delivery_round_to_cop,
    )
    rows: list[tuple[str, int, float, int]] = []
    for seed in DELIVERY_ZONE_SEEDS:
        if seed.delivery_price_cop <= config.base_price_cop:
            continue
        if "ADICIONAL" in seed.code:
            continue
        destination = CALIBRATION_DESTINATIONS.get(
            seed.code,
            f"{seed.neighborhood}, Floridablanca, Santander, Colombia",
        )
        try:
            distance_km = await client.driving_distance_km(config.origin_address, destination)
        except DomainError as exc:
            print(f"{seed.neighborhood} | ERROR | {exc}")
            continue
        if distance_km < 0.1:
            print(f"{seed.neighborhood} | {seed.delivery_price_cop} | {distance_km:.2f} | omitido")
            continue
        calculated_price = _price_from_distance(distance_km, config)
        rows.append((seed.neighborhood, seed.delivery_price_cop, distance_km, calculated_price))

    print(f"Origen: {config.origin_address}")
    print("Barrio | Precio manual | Km desde origen | Precio por bandas ORS")
    for neighborhood, price, distance_km, calculated_price in rows:
        print(f"{neighborhood} | {price} | {distance_km:.2f} | {calculated_price}")

    if rows:
        suggested = int(round(median((row[1] - config.base_price_cop) / row[2] for row in rows) / 100) * 100)
        print("")
        print(f"Referencia lineal sugerida DELIVERY_PRICE_PER_KM_COP={suggested}")
        print("El bot usa bandas calibradas para parecerse mas al recibo.")


if __name__ == "__main__":
    asyncio.run(main())
