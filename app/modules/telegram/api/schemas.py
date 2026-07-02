"""Pydantic DTOs for API/AI boundaries. They validate transport data without leaking framework concerns into domain code."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TelegramChatSchema(BaseModel):
    id: int
    first_name: str | None = None
    username: str | None = None
    type: str | None = None


class TelegramUserSchema(BaseModel):
    id: int | None = None
    is_bot: bool | None = None
    first_name: str | None = None
    username: str | None = None


class TelegramMessageSchema(BaseModel):
    message_id: int
    chat: TelegramChatSchema
    from_user: TelegramUserSchema | None = Field(default=None, alias="from")
    text: str | None = None
    date: int | None = None

    @property
    def message_type(self) -> str:
        if self.text is not None:
            return "text"
        return "unsupported"


class TelegramUpdateSchema(BaseModel):
    update_id: int
    message: TelegramMessageSchema | None = None

    @property
    def chat_id(self) -> int:
        if self.message is None:
            raise ValueError("telegram update does not contain a message")
        return self.message.chat.id

    @property
    def message_id(self) -> int:
        if self.message is None:
            raise ValueError("telegram update does not contain a message")
        return self.message.message_id

    @property
    def text(self) -> str:
        if self.message is None:
            return ""
        return self.message.text or ""

    @property
    def first_name(self) -> str | None:
        if self.message is None:
            return None
        return self.message.from_user.first_name if self.message.from_user else None

    @property
    def username(self) -> str | None:
        if self.message is None:
            return None
        return self.message.from_user.username if self.message.from_user else None

    @property
    def message_type(self) -> str:
        if self.message is None:
            return "unsupported"
        return self.message.message_type

