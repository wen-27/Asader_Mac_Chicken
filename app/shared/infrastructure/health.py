"""Health-check helpers that verify optional runtime dependencies without mixing them into business code."""

from __future__ import annotations

from sqlalchemy import text

from app.config.settings import Settings
from app.shared.infrastructure.database.session import AsyncSessionFactory


async def check_postgres() -> bool:
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def check_redis(settings: Settings) -> bool:
    try:
        from redis.asyncio import Redis

        client = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            return bool(await client.ping())
        finally:
            await client.aclose()
    except Exception:
        return False


async def check_chromadb(settings: Settings) -> bool:
    try:
        import chromadb

        client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
        client.heartbeat()
        return True
    except Exception:
        return False

