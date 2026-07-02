"""Redis idempotency adapter used to ignore duplicate Telegram updates."""

from __future__ import annotations

class RedisIdempotency:
    PROCESSING_VALUE = "processing"
    PROCESSED_VALUE = "processed"

    def __init__(self, cache) -> None:
        self._cache = cache

    async def _get_client(self):
        return await self._cache._get_client()

    async def mark_processing(self, key: str, ttl_seconds: int) -> bool:
        client = await self._get_client()
        return bool(await client.set(key, self.PROCESSING_VALUE, ex=ttl_seconds, nx=True))

    async def mark_processed(self, key: str, ttl_seconds: int) -> None:
        client = await self._get_client()
        await client.set(key, self.PROCESSED_VALUE, ex=ttl_seconds)

    async def is_processed(self, key: str) -> bool:
        client = await self._get_client()
        return await client.get(key) == self.PROCESSED_VALUE

