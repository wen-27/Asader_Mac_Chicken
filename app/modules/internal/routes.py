from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.config.settings import Settings, get_settings
from app.modules.telegram.infrastructure.models import TelegramMessageORM
from app.modules.whatsapp.infrastructure.media_cache import get_cached_or_fetch_whatsapp_media
from app.modules.whatsapp.infrastructure.whatsapp_cloud_client import WhatsAppCloudClient
from app.shared.domain.value_object import ChatId
from app.shared.infrastructure.database.session import get_async_session
from app.shared.utils.text_normalizer import normalize_text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/internal", tags=["internal"])


class SendMessageRequest(BaseModel):
    chat_id: str = Field(alias="chatId")
    body: str
    with_buttons: bool = Field(default=False, alias="withButtons")


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
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _: Annotated[None, Depends(validate_internal_api_key)],
) -> dict[str, object]:
    chat_id = ChatId(_phone_to_chat_id(payload.chat_id))
    client = WhatsAppCloudClient(settings)
    if payload.with_buttons:
        sent_message = await client.send_yes_no_message(chat_id, payload.body)
    else:
        sent_message = await client.send_text_message(chat_id, payload.body)
    session.add(
        TelegramMessageORM(
            update_id=0,
            chat_id=sent_message.chat_id.value,
            direction="outbound",
            message_text=sent_message.text_raw,
            normalized_message_text=normalize_text(sent_message.text_raw),
            message_type="admin_text",
            telegram_message_id=sent_message.message_id,
            created_at=sent_message.received_at,
        )
    )
    await session.commit()
    return {"ok": True}


@router.get("/media/{media_id}")
async def get_internal_media(
    media_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[None, Depends(validate_internal_api_key)],
) -> Response:
    try:
        content, media_type = await get_cached_or_fetch_whatsapp_media(settings, media_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="whatsapp media request failed",
        ) from exc
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


def _phone_to_chat_id(value: str) -> int:
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="chatId must contain a WhatsApp phone number",
        )
    return int(digits)
