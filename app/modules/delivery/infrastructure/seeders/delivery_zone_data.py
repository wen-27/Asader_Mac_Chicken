"""Canonical delivery-zone seed data and manual prices from the restaurant table."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeliveryZoneSeed:
    code: str
    neighborhood: str
    delivery_price_cop: int
    is_active: bool = True


DELIVERY_ZONE_SEEDS: tuple[DeliveryZoneSeed, ...] = (
    DeliveryZoneSeed("DOMICILIO_LAGOS_2_SANTA_COLOMA", "Lagos 2 / Santa Coloma", 2000),
    DeliveryZoneSeed("DOMICILIO_BUCARICA_BELLAVISTA", "Bucarica / Bellavista", 4000),
    DeliveryZoneSeed("DOMICILIO_EL_MANANTIAL", "El Manantial", 4000),
    DeliveryZoneSeed("DOMICILIO_CANAVERAL_FLORIDA", "Cañaveral / Florida", 6000),
    DeliveryZoneSeed("DOMICILIO_PROVENZA_DIAMANTE", "Provenza / Diamante", 7000),
    DeliveryZoneSeed("DOMICILIO_CACIQUE", "Cacique", 8000),
    DeliveryZoneSeed("DOMICILIO_SAN_ANDRESITO", "San Andresito", 10000),
    DeliveryZoneSeed("DOMICILIO_CIUDADELA", "Ciudadela", 11000),
    DeliveryZoneSeed("DOMICILIO_CABECERA", "Cabecera", 12000),
    DeliveryZoneSeed("HOSPITAL_INTERNACIONAL", "Hospital Internacional", 10000),
    DeliveryZoneSeed("DOMICILIO_GIRON_SAN_ANTONIO_CARRIZAL", "San Antonio Carrizal, Girón", 12000),
    DeliveryZoneSeed("DOMICILIO_ADICIONAL", "Domicilio adicional", 500),
)


EXPECTED_DELIVERY_PRICE_BY_CODE: dict[str, int] = {
    seed.code: seed.delivery_price_cop for seed in DELIVERY_ZONE_SEEDS
}
