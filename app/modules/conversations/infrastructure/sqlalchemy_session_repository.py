"""Conversation orchestration code. It should coordinate state transitions and delegate business work to use cases/services."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.conversations.domain.telegram_session import TelegramSession
from app.modules.conversations.infrastructure.mappers import (
    session_from_orm,
    session_to_orm,
    update_session_orm,
)
from app.modules.conversations.infrastructure.models import TelegramSessionORM
from app.shared.domain.value_object import ChatId


class SqlAlchemyTelegramSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_chat_id(self, chat_id: ChatId) -> TelegramSession | None:
        result = await self.session.execute(
            select(TelegramSessionORM).where(TelegramSessionORM.chat_id == chat_id.value)
        )
        row = result.scalar_one_or_none()
        return session_from_orm(row) if row else None

    async def add(self, session: TelegramSession) -> TelegramSession:
        row = session_to_orm(session)
        self.session.add(row)
        await self.session.flush()
        return session_from_orm(row)

    async def save(self, session: TelegramSession) -> TelegramSession:
        result = await self.session.execute(
            select(TelegramSessionORM).where(TelegramSessionORM.chat_id == session.chat_id.value)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return await self.add(session)
        update_session_orm(row, session)
        await self.session.flush()
        return session_from_orm(row)

