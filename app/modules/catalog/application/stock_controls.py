"""Operational stock controls for menu products and chicken variants."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.config.settings import Settings
from app.modules.catalog.domain.product import Product
from app.modules.catalog.domain.specifications import ProductAvailabilitySpecification


@dataclass(frozen=True)
class StockControl:
    code: str
    label: str
    group_label: str
    product_code: str | None
    variant_label: str | None
    is_available: bool


@dataclass(frozen=True)
class AvailabilityResult:
    is_available: bool
    product_name: str
    alternatives: tuple[str, ...] = ()
    reason: str = "available"


class StockControlRepository(Protocol):
    async def list_controls(self) -> list[StockControl]:
        ...

    async def set_available(self, code: str, is_available: bool) -> StockControl | None:
        ...


class OperationalAvailabilityService:
    def __init__(self, repository: StockControlRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    async def list_controls(self) -> list[StockControl]:
        return await self._repository.list_controls()

    async def set_available(self, code: str, is_available: bool) -> StockControl | None:
        return await self._repository.set_available(code, is_available)

    async def evaluate(
        self,
        product: Product,
        business_date: date,
        variant_label: str | None = None,
    ) -> AvailabilityResult:
        controls = await self._controls_by_code()
        return await self.evaluate_with_controls(product, business_date, controls, variant_label)

    async def evaluate_with_controls(
        self,
        product: Product,
        business_date: date,
        controls: dict[str, StockControl],
        variant_label: str | None = None,
    ) -> AvailabilityResult:
        base = ProductAvailabilitySpecification(is_holiday=self._is_monday_holiday)
        if not base.is_satisfied_by(product, business_date):
            return AvailabilityResult(
                is_available=False,
                product_name=_display_name(product, variant_label),
                alternatives=self.alternatives_for_controls(controls, product.code.value, variant_label, business_date),
                reason="restricted",
            )

        product_code = product.code.value
        if product_code.startswith("ASADO") and not _is_enabled(controls, "ASADO_FAMILY"):
            return AvailabilityResult(
                is_available=False,
                product_name=_display_name(product, variant_label),
                alternatives=self.alternatives_for_controls(controls, "ASADO_FAMILY", variant_label, business_date),
                reason="out_of_stock",
            )

        product_control = controls.get(product_code)
        if product_control is not None and not product_control.is_available:
            return AvailabilityResult(
                is_available=False,
                product_name=_display_name(product, variant_label),
                alternatives=self.alternatives_for_controls(controls, product_code, variant_label, business_date),
                reason="out_of_stock",
            )

        variant_code = stock_code_for_variant(product_code, variant_label)
        if variant_code and not _is_enabled(controls, variant_code):
            return AvailabilityResult(
                is_available=False,
                product_name=_display_name(product, variant_label),
                alternatives=self.alternatives_for_controls(controls, product_code, variant_label, business_date),
                reason="out_of_stock",
            )

        return AvailabilityResult(is_available=True, product_name=_display_name(product, variant_label))

    async def product_is_available(self, product: Product, business_date: date) -> bool:
        return (await self.evaluate(product, business_date)).is_available

    async def alternatives_for(
        self,
        product_code: str,
        variant_label: str | None = None,
        business_date: date | None = None,
    ) -> tuple[str, ...]:
        controls = await self._controls_by_code()
        return self.alternatives_for_controls(controls, product_code, variant_label, business_date)

    def alternatives_for_controls(
        self,
        controls: dict[str, StockControl],
        product_code: str,
        variant_label: str | None = None,
        business_date: date | None = None,
    ) -> tuple[str, ...]:
        alternatives = _ALTERNATIVES.get(stock_code_for_variant(product_code, variant_label) or product_code, ())
        return tuple(
            label
            for code, label in alternatives
            if _is_effectively_enabled(controls, code)
            and self._is_allowed_by_calendar(code, business_date)
        )

    async def soup_is_available(self) -> bool:
        controls = await self._controls_by_code()
        return _is_enabled(controls, "SOPA_ADICIONAL")

    async def _controls_by_code(self) -> dict[str, StockControl]:
        return {control.code: control for control in await self._repository.list_controls()}

    def _is_monday_holiday(self, value: date) -> bool:
        if value.weekday() != 0:
            return False
        configured_dates = {
            item.strip()
            for item in self._settings.special_product_monday_holidays.split(",")
            if item.strip()
        }
        return value.isoformat() in configured_dates

    def _is_allowed_by_calendar(self, code: str, business_date: date | None) -> bool:
        if code not in {"LASAGNA_MIXTA", "MADURO_QUESO"}:
            return True
        value = business_date or date.today()
        return value.weekday() in (5, 6) or self._is_monday_holiday(value)


def stock_code_for_variant(product_code: str, variant_label: str | None) -> str | None:
    if not variant_label:
        return None
    normalized_variant = variant_label.strip().lower()
    if product_code == "ASADO_CUARTO":
        if normalized_variant == "pierna":
            return "ASADO_CUARTO_PIERNA"
        if normalized_variant == "pechuga":
            return "ASADO_CUARTO_PECHUGA"
    if product_code == "BROASTER_CUARTO":
        if normalized_variant == "pierna":
            return "BROASTER_CUARTO_PIERNA"
        if normalized_variant == "pechuga":
            return "BROASTER_CUARTO_PECHUGA"
    if product_code == "ASADO_34":
        if normalized_variant == "2 piernas y 1 pechuga":
            return "ASADO_34_2PIERNAS_1PECHUGA"
        if normalized_variant == "2 pechugas y 1 pierna":
            return "ASADO_34_2PECHUGAS_1PIERNA"
    if product_code == "BROASTER_34":
        if normalized_variant == "2 piernas y 1 pechuga":
            return "BROASTER_34_2PIERNAS_1PECHUGA"
        if normalized_variant == "2 pechugas y 1 pierna":
            return "BROASTER_34_2PECHUGAS_1PIERNA"
    return None


def _is_enabled(controls: dict[str, StockControl], code: str) -> bool:
    control = controls.get(code)
    return True if control is None else control.is_available


def _is_effectively_enabled(controls: dict[str, StockControl], code: str) -> bool:
    if code.startswith("ASADO") and code != "ASADO_FAMILY" and not _is_enabled(controls, "ASADO_FAMILY"):
        return False
    return _is_enabled(controls, code)


def _display_name(product: Product, variant_label: str | None) -> str:
    if not variant_label:
        return product.name.value
    return f"{product.name.value} - {variant_label}"


_ALTERNATIVES: dict[str, tuple[tuple[str, str], ...]] = {
    "SOPA_ADICIONAL": (
        ("PAPA_FRANCESA", "Papa Francesa"),
        ("PAPA_SALADA", "Papa o yuca salada"),
        ("YUCA_FRITA", "Yuca frita"),
        ("ADICIONAL_SALSAS", "Adicional de Salsas"),
    ),
    "MADURO_QUESO": (
        ("PAPA_FRANCESA", "Papa Francesa"),
        ("PAPA_SALADA", "Papa o yuca salada"),
        ("YUCA_FRITA", "Yuca frita"),
        ("LASAGNA_MIXTA", "Lasagna Mixta"),
    ),
    "LASAGNA_MIXTA": (
        ("MADURO_QUESO", "Maduro con Queso"),
        ("PAPA_FRANCESA", "Papa Francesa"),
        ("PAPA_SALADA", "Papa o yuca salada"),
        ("YUCA_FRITA", "Yuca frita"),
    ),
    "ASADO_CUARTO_PIERNA": (
        ("ASADO_CUARTO_PECHUGA", "1/4 Asado - Pechuga"),
        ("BROASTER_CUARTO_PIERNA", "1/4 Broaster - Pierna"),
    ),
    "ASADO_CUARTO_PECHUGA": (
        ("ASADO_CUARTO_PIERNA", "1/4 Asado - Pierna"),
        ("BROASTER_CUARTO_PECHUGA", "1/4 Broaster - Pechuga"),
    ),
    "BROASTER_CUARTO_PIERNA": (
        ("BROASTER_CUARTO_PECHUGA", "1/4 Broaster - Pechuga"),
        ("ASADO_CUARTO_PIERNA", "1/4 Asado - Pierna"),
    ),
    "BROASTER_CUARTO_PECHUGA": (
        ("BROASTER_CUARTO_PIERNA", "1/4 Broaster - Pierna"),
        ("ASADO_CUARTO_PECHUGA", "1/4 Asado - Pechuga"),
    ),
    "ASADO_34_2PIERNAS_1PECHUGA": (
        ("ASADO_34_2PECHUGAS_1PIERNA", "3/4 Asado - 2 pechugas y 1 pierna"),
        ("BROASTER_34_2PIERNAS_1PECHUGA", "3/4 Broaster - 2 piernas y 1 pechuga"),
    ),
    "ASADO_34_2PECHUGAS_1PIERNA": (
        ("ASADO_34_2PIERNAS_1PECHUGA", "3/4 Asado - 2 piernas y 1 pechuga"),
        ("BROASTER_34_2PECHUGAS_1PIERNA", "3/4 Broaster - 2 pechugas y 1 pierna"),
    ),
    "BROASTER_34_2PIERNAS_1PECHUGA": (
        ("BROASTER_34_2PECHUGAS_1PIERNA", "3/4 Broaster - 2 pechugas y 1 pierna"),
        ("ASADO_34_2PIERNAS_1PECHUGA", "3/4 Asado - 2 piernas y 1 pechuga"),
    ),
    "BROASTER_34_2PECHUGAS_1PIERNA": (
        ("BROASTER_34_2PIERNAS_1PECHUGA", "3/4 Broaster - 2 piernas y 1 pechuga"),
        ("ASADO_34_2PECHUGAS_1PIERNA", "3/4 Asado - 2 pechugas y 1 pierna"),
    ),
    "ASADO_FAMILY": (
        ("BROASTER_CUARTO_PIERNA", "1/4 Broaster - Pierna"),
        ("BROASTER_CUARTO_PECHUGA", "1/4 Broaster - Pechuga"),
        ("BROASTER_34_2PIERNAS_1PECHUGA", "3/4 Broaster - 2 piernas y 1 pechuga"),
        ("BROASTER_34_2PECHUGAS_1PIERNA", "3/4 Broaster - 2 pechugas y 1 pierna"),
    ),
    "ASADO_CUARTO": (
        ("BROASTER_CUARTO_PIERNA", "1/4 Broaster - Pierna"),
        ("BROASTER_CUARTO_PECHUGA", "1/4 Broaster - Pechuga"),
    ),
    "ASADO_34": (
        ("BROASTER_34_2PIERNAS_1PECHUGA", "3/4 Broaster - 2 piernas y 1 pechuga"),
        ("BROASTER_34_2PECHUGAS_1PIERNA", "3/4 Broaster - 2 pechugas y 1 pierna"),
    ),
}
