"""Backfill local outbound bot messages into the Node admin backend."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.config.settings import get_settings
from app.modules.telegram.infrastructure.models import TelegramMessageORM
from app.modules.whatsapp.infrastructure.admin_backend_message_client import AdminBackendMessageClient
from app.shared.infrastructure.database.session import AsyncSessionFactory


async def main() -> None:
    settings = get_settings()
    if not settings.admin_backend_sync_enabled:
        raise SystemExit("ADMIN_BACKEND_SYNC_ENABLED must be true to run this backfill.")
    if not settings.internal_api_key:
        raise SystemExit("INTERNAL_API_KEY is required to run this backfill.")

    client = AdminBackendMessageClient(settings)
    synced = 0
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(TelegramMessageORM)
            .where(TelegramMessageORM.direction == "outbound")
            .order_by(TelegramMessageORM.created_at.asc(), TelegramMessageORM.id.asc())
        )
        messages = result.scalars().all()
        for message in messages:
            await client.record_bot_message(
                chat_id=str(message.chat_id),
                body=message.message_text,
                external_message_id=f"fastapi:telegram-message:{message.id}",
                sent_at=message.created_at.isoformat(),
            )
            synced += 1

    print(f"Synced {synced} bot messages to admin backend.")


if __name__ == "__main__":
    asyncio.run(main())
