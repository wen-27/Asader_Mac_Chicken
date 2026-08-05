"""Reminders for orders waiting for customer confirmation."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.config.settings import Settings
from app.modules.admin.realtime import admin_realtime_hub
from app.modules.conversations.domain.conversation_state import ConversationState
from app.modules.conversations.infrastructure.mappers import PENDING_ORDER_MARKER
from app.modules.conversations.infrastructure.models import TelegramSessionORM
from app.modules.telegram.infrastructure.models import TelegramMessageORM
from app.modules.whatsapp.infrastructure.whatsapp_cloud_client import WhatsAppCloudClient
from app.shared.domain.value_object import ChatId
from app.shared.infrastructure.database.session import AsyncSessionFactory


logger = logging.getLogger(__name__)

CHECKOUT_CONFIRMATION_REMINDER_TEXT = (
    "Hola, con mucho gusto seguimos atentos a tu orden. "
    "Para continuar, por favor confirma si deseas seguir con la orden.\n\n"
    "Selecciona SI para confirmar o NO para cancelar."
)
CHECKOUT_CONFIRMATION_REMINDER_KIND = "checkout_confirmation_reminder"
MISSING_CUSTOMER_DATA_REMINDER_KIND = "missing_customer_data_reminder"


async def run_checkout_confirmation_reminder_loop(
    settings: Settings,
    stop_event: asyncio.Event,
) -> None:
    while not stop_event.is_set():
        try:
            await send_due_checkout_confirmation_reminders(settings)
            await send_due_missing_customer_data_reminders(settings)
        except Exception:
            logger.exception("checkout confirmation reminder loop failed")
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=60)


async def send_due_checkout_confirmation_reminders(settings: Settings) -> int:
    client = _whatsapp_client_or_none(settings)
    if client is None:
        return 0

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=5)
    today_start = datetime.combine(
        now.astimezone(ZoneInfo("America/Bogota")).date(),
        time.min,
        tzinfo=ZoneInfo("America/Bogota"),
    ).astimezone(timezone.utc)

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(TelegramSessionORM)
            .where(
                TelegramSessionORM.current_step == ConversationState.CHECKOUT_REVIEW.value,
                TelegramSessionORM.updated_at <= cutoff,
                TelegramSessionORM.updated_at >= today_start,
            )
            .order_by(TelegramSessionORM.updated_at.asc())
            .limit(50)
        )
        rows = [
            row
            for row in result.scalars().all()
            if _has_cart_items(row.cart_json)
            and _checkout_reminder_due(row.cart_json, cutoff)
        ]
        if not rows:
            return 0

        sent_count = 0
        for row in rows:
            try:
                sent_message = await client.send_text_message(
                    ChatId(row.chat_id),
                    CHECKOUT_CONFIRMATION_REMINDER_TEXT,
                )
                row.cart_json = _mark_checkout_reminder_sent(row.cart_json, now)
                session.add(
                    TelegramMessageORM(
                        update_id=0,
                        chat_id=sent_message.chat_id.value,
                        direction="outbound",
                        message_text=sent_message.text_raw,
                        normalized_message_text=sent_message.text_normalized,
                        message_type="text",
                        telegram_message_id=sent_message.message_id,
                        created_at=sent_message.received_at,
                    )
                )
                sent_count += 1
            except Exception:
                logger.exception("failed to send checkout confirmation reminder chat_id=%s", row.chat_id)
        await session.commit()
        if sent_count:
            await admin_realtime_hub.broadcast({"type": "conversations.changed"})
        return sent_count


async def send_due_missing_customer_data_reminders(settings: Settings) -> int:
    client = _whatsapp_client_or_none(settings)
    if client is None:
        return 0

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=3)
    today_start = datetime.combine(
        now.astimezone(ZoneInfo("America/Bogota")).date(),
        time.min,
        tzinfo=ZoneInfo("America/Bogota"),
    ).astimezone(timezone.utc)

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(TelegramSessionORM)
            .where(
                TelegramSessionORM.current_step == ConversationState.ASK_CUSTOMER_DATA.value,
                TelegramSessionORM.updated_at <= cutoff,
                TelegramSessionORM.updated_at >= today_start,
            )
            .order_by(TelegramSessionORM.updated_at.asc())
            .limit(50)
        )
        rows = [
            row
            for row in result.scalars().all()
            if _has_cart_items(row.cart_json)
            and _missing_customer_fields(row)
            and _missing_customer_data_reminder_due(row.cart_json, cutoff)
        ]
        if not rows:
            return 0

        sent_count = 0
        for row in rows:
            missing = _missing_customer_fields(row)
            if not missing:
                continue
            try:
                sent_message = await client.send_text_message(
                    ChatId(row.chat_id),
                    _missing_customer_data_reminder_text(missing),
                )
                row.cart_json = _mark_missing_customer_data_reminder_sent(row.cart_json, now)
                session.add(
                    TelegramMessageORM(
                        update_id=0,
                        chat_id=sent_message.chat_id.value,
                        direction="outbound",
                        message_text=sent_message.text_raw,
                        normalized_message_text=sent_message.text_normalized,
                        message_type="text",
                        telegram_message_id=sent_message.message_id,
                        created_at=sent_message.received_at,
                    )
                )
                sent_count += 1
            except Exception:
                logger.exception("failed to send missing customer data reminder chat_id=%s", row.chat_id)
        await session.commit()
        if sent_count:
            await admin_realtime_hub.broadcast({"type": "conversations.changed"})
        return sent_count


def _has_cart_items(cart_json: list[dict[str, object]]) -> bool:
    return any(not item.get(PENDING_ORDER_MARKER) for item in cart_json or [])


def _checkout_reminder_due(cart_json: list[dict[str, object]], cutoff: datetime) -> bool:
    marker = _checkout_reminder_marker(cart_json)
    if not marker:
        return True
    last_sent_raw = marker.get("last_sent_at")
    if not isinstance(last_sent_raw, str):
        return True
    try:
        last_sent_at = datetime.fromisoformat(last_sent_raw)
    except ValueError:
        return True
    if last_sent_at.tzinfo is None:
        last_sent_at = last_sent_at.replace(tzinfo=timezone.utc)
    return last_sent_at <= cutoff


def _missing_customer_data_reminder_due(cart_json: list[dict[str, object]], cutoff: datetime) -> bool:
    marker = _missing_customer_data_reminder_marker(cart_json)
    if not marker:
        return True
    last_sent_raw = marker.get("last_sent_at")
    if not isinstance(last_sent_raw, str):
        return True
    try:
        last_sent_at = datetime.fromisoformat(last_sent_raw)
    except ValueError:
        return True
    if last_sent_at.tzinfo is None:
        last_sent_at = last_sent_at.replace(tzinfo=timezone.utc)
    return last_sent_at <= cutoff


def _mark_checkout_reminder_sent(
    cart_json: list[dict[str, object]],
    sent_at: datetime,
) -> list[dict[str, object]]:
    values = list(cart_json or [])
    marker = _checkout_reminder_marker(values)
    if marker is None:
        values.append(
            {
                PENDING_ORDER_MARKER: True,
                "payload": {
                    "kind": CHECKOUT_CONFIRMATION_REMINDER_KIND,
                    "last_sent_at": sent_at.isoformat(),
                },
            }
        )
        return values
    marker["last_sent_at"] = sent_at.isoformat()
    return values


def _mark_missing_customer_data_reminder_sent(
    cart_json: list[dict[str, object]],
    sent_at: datetime,
) -> list[dict[str, object]]:
    values = list(cart_json or [])
    marker = _missing_customer_data_reminder_marker(values)
    if marker is None:
        values.append(
            {
                PENDING_ORDER_MARKER: True,
                "payload": {
                    "kind": MISSING_CUSTOMER_DATA_REMINDER_KIND,
                    "last_sent_at": sent_at.isoformat(),
                },
            }
        )
        return values
    marker["last_sent_at"] = sent_at.isoformat()
    return values


def _checkout_reminder_marker(cart_json: list[dict[str, object]]) -> dict[str, object] | None:
    for item in cart_json or []:
        if not item.get(PENDING_ORDER_MARKER):
            continue
        payload = item.get("payload")
        if isinstance(payload, dict) and payload.get("kind") == CHECKOUT_CONFIRMATION_REMINDER_KIND:
            return payload
    return None


def _missing_customer_data_reminder_marker(cart_json: list[dict[str, object]]) -> dict[str, object] | None:
    for item in cart_json or []:
        if not item.get(PENDING_ORDER_MARKER):
            continue
        payload = item.get("payload")
        if isinstance(payload, dict) and payload.get("kind") == MISSING_CUSTOMER_DATA_REMINDER_KIND:
            return payload
    return None


def _missing_customer_fields(row: TelegramSessionORM) -> list[str]:
    if (row.fulfillment_type or "DELIVERY") == "PICKUP":
        missing = []
        if not row.customer_name:
            missing.append("nombre completo")
        if not row.phone:
            missing.append("telefono")
        if not _has_pickup_time_observation(row.observations):
            missing.append("en cuanto tiempo pasa a recoger")
        return missing

    missing = []
    if not row.customer_name:
        missing.append("nombre completo")
    if not row.phone:
        missing.append("telefono")
    if not row.address:
        missing.append("direccion")
    if not row.neighborhood:
        missing.append("barrio")
    if not row.payment_method:
        missing.append("metodo de pago")
    return missing


def _has_pickup_time_observation(observations: str | None) -> bool:
    normalized = (observations or "").lower()
    return any(
        marker in normalized
        for marker in (
            "recoger a la",
            "recoge a la",
            "recoge en",
            "paso en",
            "pasa en",
        )
    )


def _missing_customer_data_reminder_text(missing: list[str]) -> str:
    return "\n\n".join(
        [
            "Hola, seguimos atentos a tu orden.",
            "Para poder confirmarla me falta esta informacion: " + ", ".join(missing) + ".",
            "Apenas me la envies, te muestro el resumen para confirmar.",
        ]
    )


def _whatsapp_client_or_none(settings: Settings) -> WhatsAppCloudClient | None:
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return None
    return WhatsAppCloudClient(settings)
