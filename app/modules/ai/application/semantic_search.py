"""Application service for semantic catalog lookup. It should only search products/aliases, never customer/order data."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging

from app.modules.ai.application.ports import CachePort, CatalogSemanticSearchPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CatalogSemanticMatch:
    code: str
    score: float
    text: str


class CatalogSemanticSearch:
    def __init__(
        self,
        vector_store: CatalogSemanticSearchPort,
        cache: CachePort | None = None,
        cache_ttl_seconds: int = 900,
    ) -> None:
        self._vector_store = vector_store
        self._cache = cache
        self._cache_ttl_seconds = cache_ttl_seconds

    async def search(self, query: str, limit: int = 5) -> list[CatalogSemanticMatch]:
        cache_key = f"catalog-semantic-search:{query}:{limit}"
        if self._cache is not None:
            cached = await self._cache.get_text(cache_key)
            if cached:
                return [CatalogSemanticMatch(**item) for item in json.loads(cached)]

        try:
            results = await self._vector_store.search(query, limit)
        except Exception:
            logger.warning("catalog semantic search unavailable; using deterministic parser only", exc_info=True)
            return []
        matches = [
            CatalogSemanticMatch(code=result.code, score=result.score, text=result.text)
            for result in results
        ]
        if self._cache is not None:
            await self._cache.set_text(
                cache_key,
                json.dumps([match.__dict__ for match in matches]),
                self._cache_ttl_seconds,
            )
        return matches
