"""Backfill local bot orders into the Node admin backend.

This is intentionally manual. Use it after enabling ADMIN_BACKEND_SYNC_ENABLED
when orders were confirmed while the Node admin backend was disconnected.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config.settings import get_settings
from app.modules.orders.infrastructure.admin_backend_order_client import AdminBackendOrderClient
from app.modules.orders.infrastructure.mappers import order_from_orm
from app.modules.orders.infrastructure.models import OrderORM
from app.shared.infrastructure.database.session import AsyncSessionFactory


async def main() -> None:
    settings = get_settings()
    if not settings.admin_backend_sync_enabled:
        raise SystemExit("ADMIN_BACKEND_SYNC_ENABLED must be true to run this backfill.")
    if not settings.internal_api_key:
        raise SystemExit("INTERNAL_API_KEY is required to run this backfill.")

    client = AdminBackendOrderClient(settings)
    synced = 0
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(OrderORM)
            .options(selectinload(OrderORM.items))
            .where(OrderORM.status.in_(["CONFIRMED", "PREPARING", "DELIVERED"]))
            .order_by(OrderORM.created_at.asc(), OrderORM.id.asc())
        )
        orders = result.scalars().all()
        for row in orders:
            await client.sync_confirmed_order(order_from_orm(row), row.chat_id)
            synced += 1

    print(f"Synced {synced} orders to admin backend.")


if __name__ == "__main__":
    asyncio.run(main())
