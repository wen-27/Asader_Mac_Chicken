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
        self._timeout = settings.whatsapp_send_timeout_seconds
        self._client = client

    async def send_text_message(self, chat_id: ChatId, text: str) -> TelegramMessage:
        payload = _confirmation_buttons_payload(chat_id, text)
        if payload is None:
            payload = {
                "messaging_product": "whatsapp",
                "to": str(chat_id.value),
                "type": "text",
                "text": {"body": text},
            }
        response_data = await self._send_payload(payload)
        return _sent_message(chat_id, text, response_data)

    async def send_yes_no_message(
        self,
        chat_id: ChatId,
        text: str,
        yes_id: str = "admin_preparing_yes",
        no_id: str = "admin_preparing_no",
    ) -> TelegramMessage:
        payload = _yes_no_buttons_payload(chat_id, text, yes_id=yes_id, no_id=no_id)
        response_data = await self._send_payload(payload)
        return _sent_message(chat_id, text, response_data)

    async def _send_payload(self, payload: dict[str, object]) -> dict[str, object]:
        if self._client is None:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                return await self._send(client, payload)
        return await self._send(self._client, payload)

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


def _confirmation_buttons_payload(chat_id: ChatId, text: str) -> dict[str, object] | None:
    if "Responde SI para confirmar o NO para cancelar." not in text:
        return None
    body = _confirmation_body_text(text)
    return {
        "messaging_product": "whatsapp",
        "to": str(chat_id.value),
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": "confirm_order_yes", "title": "Sí"},
                    },
                    {
                        "type": "reply",
                        "reply": {"id": "confirm_order_no", "title": "No"},
                    },
                ]
            },
        },
    }


def _confirmation_body_text(text: str) -> str:
    body = text.replace(
        "¿Deseas confirmar el pedido? Responde SI para confirmar o NO para cancelar.",
        "¿Deseas confirmar el pedido?",
    )
    body = body.replace(
        "¿Confirmas tu pedido? Responde SI para confirmar o NO para cancelar.",
        "¿Confirmas tu pedido?",
    )
    body = body.replace(
        "\n\nResponde SI para confirmar o NO para cancelar.",
        "",
    )
    body = body.replace(
        " Responde SI para confirmar o NO para cancelar.",
        "",
    )
    return body.strip()


def _yes_no_buttons_payload(chat_id: ChatId, text: str, yes_id: str, no_id: str) -> dict[str, object]:
    return {
        "messaging_product": "whatsapp",
        "to": str(chat_id.value),
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": text},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": yes_id, "title": "Sí"},
                    },
                    {
                        "type": "reply",
                        "reply": {"id": no_id, "title": "No"},
                    },
                ]
            },
        },
    }


def _sent_message(
    chat_id: ChatId,
    text: str,
    response_data: dict[str, object],
) -> TelegramMessage:
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

def _numeric_message_id(value: str) -> int:
    if not value:
        return 1
    import hashlib

    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:15], 16)
