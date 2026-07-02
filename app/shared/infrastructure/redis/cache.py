"""Redis cache adapter for short-lived text/JSON values. Redis is an accelerator, not the source of truth."""

from __future__ import annotations

from app.config.settings import Settings


class RedisTextCache:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None

    async def _get_client(self):
        if self._client is None:
            from redis.asyncio import Redis

            self._client = Redis.from_url(self._settings.redis_url, decode_responses=True)
        return self._client

    async def get_text(self, key: str) -> str | None:
        client = await self._get_client()
        value = await client.get(key)
        return str(value) if value is not None else None

    async def set_text(self, key: str, value: str, ttl_seconds: int) -> None:
        client = await self._get_client()
        await client.set(key, value, ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        client = await self._get_client()
        await client.delete(key)

