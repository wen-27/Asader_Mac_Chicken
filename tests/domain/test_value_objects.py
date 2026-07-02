"""Pure domain model. This file must not depend on FastAPI, SQLAlchemy, Redis, ChromaDB or Telegram."""

from __future__ import annotations

import pytest

from app.shared.domain.exceptions import InvalidValueError
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import ProductCode


def test_money_cop_rejects_negative_amounts() -> None:
    with pytest.raises(InvalidValueError):
        MoneyCOP(-1)


def test_money_cop_rejects_float_amounts() -> None:
    with pytest.raises(InvalidValueError):
        MoneyCOP(1000.5)  # type: ignore[arg-type]


def test_product_code_normalizes_to_uppercase() -> None:
    code = ProductCode(" asado entero ")

    assert code.value == "ASADO_ENTERO"

