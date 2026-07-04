from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.config.settings import Settings, get_settings
from app.modules.telegram.infrastructure.telegram_http_client import TelegramHttpClient
from app.shared.domain.value_object import ChatId

router = APIRouter(prefix="/internal", tags=["internal"])


class SendMessageRequest(BaseModel):
    chat_id: str = Field(alias="chatId")
    body: str


def validate_internal_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    api_key: Annotated[str | None, Header(alias="X-Internal-Api-Key")] = None,
) -> None:
    if not settings.internal_api_key or api_key != settings.internal_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid internal api key",
        )


@router.post("/messages/send")
async def send_internal_message(
    payload: SendMessageRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[None, Depends(validate_internal_api_key)],
) -> dict[str, object]:
    await TelegramHttpClient(settings).send_text_message(ChatId(int(payload.chat_id)), payload.body)
    return {"ok": True}
