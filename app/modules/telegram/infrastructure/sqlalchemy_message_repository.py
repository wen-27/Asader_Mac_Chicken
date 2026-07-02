"""SQLAlchemy repository adapter. Keep queries here and business rules in domain/application code."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.telegram.domain.telegram_message import TelegramMessage
from app.modules.telegram.infrastructure.mappers import message_from_orm, message_to_orm
from app.modules.telegram.infrastructure.models import TelegramMessageORM
from app.shared.domain.value_object import ChatId


class SqlAlchemyTelegramMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, message: TelegramMessage, direction: str = "inbound") -> TelegramMessage:
        row = message_to_orm(message, direction)
        self.session.add(row)
        await self.session.flush()
        return message_from_orm(row)

    async def get_inbound_by_update_id(self, update_id: int) -> TelegramMessage | None:
        result = await self.session.execute(
            select(TelegramMessageORM).where(
                TelegramMessageORM.update_id == update_id,
                TelegramMessageORM.direction == "inbound",
            )
        )
        row = result.scalar_one_or_none()
        return message_from_orm(row) if row else None

    async def list_by_chat_id(self, chat_id: ChatId, limit: int = 50) -> list[TelegramMessage]:
        result = await self.session.execute(
            select(TelegramMessageORM)
            .where(TelegramMessageORM.chat_id == chat_id.value)
            .order_by(TelegramMessageORM.created_at.desc())
            .limit(limit)
        )
        return [message_from_orm(row) for row in result.scalars().all()]
