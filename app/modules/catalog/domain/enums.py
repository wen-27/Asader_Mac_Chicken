"""Domain enums shared by entities and use cases. Add values carefully because persisted rows may depend on them."""

from __future__ import annotations

from enum import Enum


class ProductCategory(str, Enum):
    POLLO_ASADO = "POLLO_ASADO"
    POLLO_BROASTER = "POLLO_BROASTER"
    BEBIDAS = "BEBIDAS"
    BEBIDAS_ALCOHOLICAS = "BEBIDAS_ALCOHOLICAS"
    ESPECIALES = "ESPECIALES"
    ADICIONALES = "ADICIONALES"
    HELADOS = "HELADOS"
    DOMICILIOS = "DOMICILIOS"
    METODOS_PAGO = "METODOS_PAGO"
    OTROS = "OTROS"


class ProductRestriction(str, Enum):
    NONE = "NONE"
    WEEKEND_OR_HOLIDAY = "WEEKEND_OR_HOLIDAY"
