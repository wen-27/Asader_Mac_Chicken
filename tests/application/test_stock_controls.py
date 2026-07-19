"""Tests for operational stock controls used by the conversation bot."""

from __future__ import annotations

from datetime import date

import pytest

from app.config.settings import Settings
from app.modules.catalog.application.stock_controls import (
    OperationalAvailabilityService,
    StockControl,
)
from app.modules.catalog.domain.enums import ProductCategory
from app.modules.catalog.domain.product import Product
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import ProductCode, ProductName


class FakeStockControlRepository:
    def __init__(self, controls: list[StockControl]) -> None:
        self.controls = controls

    async def list_controls(self) -> list[StockControl]:
        return self.controls

    async def set_available(self, code: str, is_available: bool) -> StockControl | None:
        return None


@pytest.mark.asyncio
async def test_three_quarter_variant_disabled_by_stock_control_is_unavailable() -> None:
    product = Product(
        code=ProductCode("ASADO_34"),
        name=ProductName("3/4 Asado"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(34000),
    )
    service = OperationalAvailabilityService(
        FakeStockControlRepository(
            [
                StockControl(
                    code="ASADO_34_2PECHUGAS_1PIERNA",
                    label="3/4 Asado - 2 pechugas y 1 pierna",
                    group_label="3/4 Asado",
                    product_code="ASADO_34",
                    variant_label="2 pechugas y 1 pierna",
                    is_available=False,
                )
            ]
        ),
        Settings(),
    )

    result = await service.evaluate(product, date(2026, 7, 4), "2 pechugas y 1 pierna")

    assert not result.is_available
    assert result.reason == "out_of_stock"
    assert result.product_name == "3/4 Asado - 2 pechugas y 1 pierna"
