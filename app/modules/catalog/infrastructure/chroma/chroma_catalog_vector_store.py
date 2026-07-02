"""ChromaDB catalog vector-store adapter. Chroma stores searchable catalog text, not transactional data."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from app.config.settings import Settings
from app.modules.ai.application.semantic_search import CatalogSemanticMatch
from app.modules.catalog.application.vector_indexer import CatalogVectorDocument
from app.shared.utils.text_normalizer import normalize_text


@dataclass(frozen=True)
class ChromaCatalogVectorStoreConfig:
    collection_name: str = "asadero_mc_catalog"


class ChromaCatalogVectorStore:
    def __init__(
        self,
        settings: Settings,
        config: ChromaCatalogVectorStoreConfig | None = None,
    ) -> None:
        self._settings = settings
        self._config = config or ChromaCatalogVectorStoreConfig()

    def _collection(self):
        import chromadb

        client = chromadb.HttpClient(
            host=self._settings.chroma_host,
            port=self._settings.chroma_port,
        )
        return client.get_or_create_collection(self._config.collection_name)

    def _embedding(self, text: str, dimensions: int = 128) -> list[float]:
        normalized = normalize_text(text)
        vector = [0.0] * dimensions
        tokens = normalized.split()
        features = tokens + [normalized[index : index + 3] for index in range(max(0, len(normalized) - 2))]
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    async def reindex(self, documents: list[CatalogVectorDocument]) -> int:
        collection = self._collection()
        if not documents:
            return 0
        ids = [document.id for document in documents]
        try:
            collection.delete(ids=ids)
        except Exception:
            pass
        collection.add(
            ids=ids,
            documents=[document.text for document in documents],
            embeddings=[self._embedding(document.text) for document in documents],
            metadatas=[document.metadata for document in documents],
        )
        return len(documents)

    async def search(self, query: str, limit: int = 5) -> list[CatalogSemanticMatch]:
        collection = self._collection()
        raw_results = collection.query(query_embeddings=[self._embedding(query)], n_results=limit)
        documents = raw_results.get("documents", [[]])[0]
        metadatas = raw_results.get("metadatas", [[]])[0]
        distances = raw_results.get("distances", [[]])[0]
        matches: list[CatalogSemanticMatch] = []
        for index, metadata in enumerate(metadatas):
            distance = float(distances[index]) if index < len(distances) else 1.0
            score = max(0.0, 1.0 - distance)
            matches.append(
                CatalogSemanticMatch(
                    code=str(metadata.get("code", "")),
                    score=score,
                    text=str(documents[index]) if index < len(documents) else "",
                )
            )
        return matches
