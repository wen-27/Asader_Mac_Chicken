"""Application port definitions. These protocols keep use cases independent from database, Redis, Telegram and API clients."""

from __future__ import annotations

from typing import Protocol

from app.modules.ai.application.schemas import NaturalLanguageOrderParse


class LLMClient(Protocol):
    async def complete(self, prompt: str) -> str:
        ...


class NaturalLanguageOrderParser(Protocol):
    async def parse(self, message: str, catalog_context: str) -> NaturalLanguageOrderParse:
        ...


class SemanticSearchResult(Protocol):
    code: str
    score: float
    text: str


class CatalogSemanticSearchPort(Protocol):
    async def search(self, query: str, limit: int = 5) -> list[SemanticSearchResult]:
        ...


class CachePort(Protocol):
    async def get_text(self, key: str) -> str | None:
        ...

    async def set_text(self, key: str, value: str, ttl_seconds: int) -> None:
        ...

