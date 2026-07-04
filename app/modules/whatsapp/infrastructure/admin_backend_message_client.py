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

    async def record_incoming_message(
        self,
        *,
        chat_id: str,
        phone: str,
        body: str,
        external_message_id: str,
    ) -> None:
        if not self._api_key:
            logger.warning("internal api key is not configured; skipping incoming message sync")
            return

        payload = {
            "chatId": chat_id,
            "phone": phone,
            "body": body,
            "externalMessageId": external_message_id,
        }

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{self._base_url}/messages/incoming",
                json=payload,
                headers={"X-Internal-Api-Key": self._api_key},
            )
            response.raise_for_status()
