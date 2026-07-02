"""Mapping helpers between pure domain objects and infrastructure/ORM records."""

from __future__ import annotations

from app.modules.catalog.domain.product_alias import normalize_alias
from app.modules.delivery.domain.delivery_zone import DeliveryZone
from app.modules.delivery.infrastructure.models import DeliveryZoneORM
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import Neighborhood


def zone_to_orm(zone: DeliveryZone) -> DeliveryZoneORM:
    return DeliveryZoneORM(
        code=zone.code,
        neighborhood=zone.neighborhood.value,
        normalized_neighborhood=normalize_alias(zone.neighborhood.value),
        delivery_price_cop=zone.delivery_price.amount,
        is_active=zone.is_active,
    )


def zone_from_orm(row: DeliveryZoneORM) -> DeliveryZone:
    return DeliveryZone(
        code=row.code,
        neighborhood=Neighborhood(row.neighborhood),
        delivery_price=MoneyCOP(row.delivery_price_cop),
        is_active=row.is_active,
    )

