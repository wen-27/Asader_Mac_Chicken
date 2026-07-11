"""Internal client that mirrors WhatsApp inbound messages into the admin backend."""

from __future__ import annotations

import logging

import httpx

from app.config.settings import Settings

logger = logging.getLogger(__name__)


class AdminBackendMessageClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.admin_backend_base_url.rstrip("/")
        self._api_key = settings.internal_api_key
        self._enabled = settings.admin_backend_sync_enabled
        self._timeout = settings.admin_backend_timeout_seconds

    async def record_incoming_message(
        self,
        *,
        chat_id: str,
        phone: str,
        body: str,
        external_message_id: str,
    ) -> None:
        if not self._enabled or not self._api_key:
            return

        payload = {
            "chatId": chat_id,
            "phone": phone,
            "body": body,
            "externalMessageId": external_message_id,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/messages/incoming",
                json=payload,
                headers={"X-Internal-Api-Key": self._api_key},
            )
            response.raise_for_status()

    async def record_bot_message(
        self,
        *,
        chat_id: str,
        body: str,
        external_message_id: str | None = None,
    ) -> None:
        if not self._enabled or not self._api_key:
            return

        payload = {
            "chatId": chat_id,
            "body": body,
            "externalMessageId": external_message_id,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/messages/outgoing-bot",
                json=payload,
                headers={"X-Internal-Api-Key": self._api_key},
            )
            response.raise_for_status()

    async def get_conversation_control(self, *, chat_id: str) -> dict[str, object]:
        if not self._enabled or not self._api_key:
            return {"aiActive": True}

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/conversations/{chat_id}/control",
                headers={"X-Internal-Api-Key": self._api_key},
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict) and isinstance(data.get("data"), dict):
                return data["data"]
        return {"aiActive": True}
