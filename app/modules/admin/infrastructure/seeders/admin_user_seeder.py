"""Idempotent admin user seeder."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings
from app.modules.admin.infrastructure.models import AdminUserORM
from app.modules.admin.infrastructure.passwords import hash_password


@dataclass(frozen=True)
class AdminUserSeedResult:
    users_upserted: int
    email: str


async def seed_admin_user(session: AsyncSession, settings: Settings) -> AdminUserSeedResult:
    email = settings.admin_email.strip().lower()
    name = settings.admin_name.strip() or "Administrador"
    password = settings.admin_password

    result = await session.execute(select(AdminUserORM).where(AdminUserORM.email == email))
    row = result.scalar_one_or_none()
    password_hash = hash_password(password)
    if row is None:
        session.add(
            AdminUserORM(
                email=email,
                name=name,
                password_hash=password_hash,
                is_active=True,
            )
        )
    else:
        row.name = name
        row.password_hash = password_hash
        row.is_active = True

    await session.flush()
    return AdminUserSeedResult(users_upserted=1, email=email)
