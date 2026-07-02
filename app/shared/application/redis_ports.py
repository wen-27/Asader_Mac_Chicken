"""Redis-related application ports for cache, idempotency and locks."""

from __future__ import annotations

from typing import Protocol


class RedisCachePort(Protocol):
    async def get_text(self, key: str) -> str | None:
        ...

    async def set_text(self, key: str, value: str, ttl_seconds: int) -> None:
        ...

    async def delete(self, key: str) -> None:
        ...


class RedisIdempotencyPort(Protocol):
    async def mark_processing(self, key: str, ttl_seconds: int) -> bool:
        ...

    async def mark_processed(self, key: str, ttl_seconds: int) -> None:
        ...

    async def is_processed(self, key: str) -> bool:
        ...


class RedisLockPort(Protocol):
    async def acquire(self, key: str, ttl_seconds: int) -> str | None:
        ...

    async def release(self, key: str, token: str) -> None:
        ...

