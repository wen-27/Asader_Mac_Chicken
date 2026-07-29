"""Database seeding entrypoint for catalog, aliases and delivery zones. Seeders are intentionally idempotent."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.shared.infrastructure.database.seed import seed_database
from app.shared.infrastructure.database.session import AsyncSessionFactory


async def main() -> None:
    async with AsyncSessionFactory() as session:
        result = await seed_database(session)
        await session.commit()

    print(
        "Seed completed: "
        f"{result.admin_user.users_upserted} admin user ({result.admin_user.email}), "
        f"{result.catalog.products_upserted} products, "
        f"{result.catalog.aliases_upserted} aliases, "
        f"{result.delivery_zones.zones_upserted} delivery zones."
    )


if __name__ == "__main__":
    asyncio.run(main())
