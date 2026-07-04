"""WhatsApp Cloud API HTTP adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config.settings import Settings
from app.modules.telegram.domain.telegram_message import TelegramMessage
from app.shared.domain.exceptions import InvalidValueError
from app.shared.domain.value_object import ChatId
from app.shared.utils.text_normalizer import normalize_text


class WhatsAppCloudClient:
    def __init__(self, settings: Settings, client: Optional[httpx.AsyncClient] = None) -> None:
        if not settings.whatsapp_access_token:
            raise InvalidValueError("whatsapp access token is not configured")
        if not settings.whatsapp_phone_number_id:
            raise InvalidValueError("whatsapp phone number id is not configured")
        self._url = (
            f"https://graph.facebook.com/{settings.whatsapp_graph_api_version}/"
            f"{settings.whatsapp_phone_number_id}/messages"
        )
        self._access_token = settings.whatsapp_access_token
        self._client = client

    async def send_text_message(self, chat_id: ChatId, text: str) -> TelegramMessage:
        payload = {
            "messaging_product": "whatsapp",
            "to": str(chat_id.value),
            "type": "text",
            "text": {"body": text},
        }
        if self._client is None:
            async with httpx.AsyncClient(timeout=10) as client:
                response_data = await self._send(client, payload)
        else:
            response_data = await self._send(self._client, payload)

        messages = response_data.get("messages", [])
        external_id = ""
        if isinstance(messages, list) and messages:
            first_message = messages[0]
            if isinstance(first_message, dict):
                external_id = str(first_message.get("id", ""))

        return TelegramMessage(
            chat_id=chat_id,
            message_id=_numeric_message_id(external_id),
            update_id=0,
            text_raw=text,
            text_normalized=normalize_text(text),
            received_at=datetime.now(timezone.utc),
        )

    async def _send(self, client: httpx.AsyncClient, payload: dict[str, object]) -> dict[str, object]:
        response = await client.post(
            self._url,
            json=payload,
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            description = ""
            try:
                data = exc.response.json()
                if isinstance(data, dict):
                    error = data.get("error")
                    if isinstance(error, dict):
                        description = str(error.get("message", ""))
            except ValueError:
                description = exc.response.text[:200]
            message = f"whatsapp send message failed with status {exc.response.status_code}"
            if description:
                message = f"{message}: {description}"
            raise InvalidValueError(message) from exc
        return response.json()


def _numeric_message_id(value: str) -> int:
    if not value:
        return 1
    import hashlib

    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:15], 16)
