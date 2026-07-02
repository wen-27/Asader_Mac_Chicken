"""Pure domain model. This file must not depend on FastAPI, SQLAlchemy, Redis, ChromaDB or Telegram."""

from __future__ import annotations

from dataclasses import dataclass
import unicodedata

from app.shared.domain.exceptions import InvalidValueError
from app.shared.domain.value_object import ProductCode


def normalize_alias(value: str) -> str:
    normalized = unicodedata.normalize("NFD", str(value).strip().lower())
    without_accents = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return " ".join(without_accents.split())


@dataclass(frozen=True)
class ProductAlias:
    product_code: ProductCode
    alias: str

    def __post_init__(self) -> None:
        normalized = normalize_alias(self.alias)
        if not normalized:
            raise InvalidValueError("product alias cannot be empty")
        object.__setattr__(self, "alias", normalized)

    def matches(self, candidate: str) -> bool:
        return self.alias == normalize_alias(candidate)

