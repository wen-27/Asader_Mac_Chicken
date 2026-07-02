"""Telegram Bot API HTTP adapter implemented with async httpx."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config.settings import Settings
from app.modules.telegram.domain.telegram_message import TelegramMessage
from app.shared.domain.exceptions import InvalidValueError
from app.shared.domain.value_object import ChatId
from app.shared.utils.text_normalizer import normalize_text


class TelegramHttpClient:
    def __init__(self, settings: Settings, client: Optional[httpx.AsyncClient] = None) -> None:
        if not settings.telegram_bot_token:
            raise InvalidValueError("telegram bot token is not configured")
        self._base_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
        self._client = client

    async def send_text_message(self, chat_id: ChatId, text: str) -> TelegramMessage:
        payload = {"chat_id": chat_id.value, "text": text}
        if self._client is None:
            async with httpx.AsyncClient(timeout=10) as client:
                response_data = await self._send(client, payload)
        else:
            response_data = await self._send(self._client, payload)

        result = response_data.get("result", {})
        message_id = int(result.get("message_id", 0))
        message_text = str(result.get("text", text))
        return TelegramMessage(
            chat_id=chat_id,
            message_id=message_id,
            update_id=0,
            text_raw=message_text,
            text_normalized=normalize_text(message_text),
            received_at=datetime.now(timezone.utc),
        )

    async def _send(self, client: httpx.AsyncClient, payload: dict[str, object]) -> dict[str, object]:
        response = await client.post(f"{self._base_url}/sendMessage", json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            description = ""
            try:
                data = exc.response.json()
                if isinstance(data, dict):
                    description = str(data.get("description", ""))
            except ValueError:
                description = exc.response.text[:200]
            message = f"telegram sendMessage failed with status {exc.response.status_code}"
            if description:
                message = f"{message}: {description}"
            raise InvalidValueError(message) from exc
        return response.json()
