"""Redis lock adapter used to serialize per-chat Telegram processing."""

from __future__ import annotations

from uuid import uuid4


RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class RedisLock:
    def __init__(self, cache) -> None:
        self._cache = cache

    async def _get_client(self):
        return await self._cache._get_client()

    async def acquire(self, key: str, ttl_seconds: int) -> str | None:
        client = await self._get_client()
        token = uuid4().hex
        acquired = await client.set(key, token, ex=ttl_seconds, nx=True)
        return token if acquired else None

    async def release(self, key: str, token: str) -> None:
        client = await self._get_client()
        await client.eval(RELEASE_LOCK_SCRIPT, 1, key, token)

