"""Payment proof rules for transfer-based orders."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.settings import Settings
from app.modules.admin.realtime import admin_realtime_hub
from app.modules.orders.infrastructure.models import OrderORM
from app.modules.telegram.infrastructure.models import TelegramMessageORM
from app.modules.whatsapp.infrastructure.whatsapp_cloud_client import WhatsAppCloudClient
from app.shared.domain.value_object import ChatId
from app.shared.infrastructure.database.session import AsyncSessionFactory

logger = logging.getLogger(__name__)

PAYMENT_PROOF_REMINDER_TEXT = (
    "Estimado cliente, agradecemos el envio de tu comprobante para proceder "
    "con la preparacion del pedido."
)
PAYMENT_PROOF_RECEIVED_TEXT = (
    "✅ Comprobante recibido. Ya podemos proceder con la preparacion de tu pedido."
)


def payment_requires_proof(payment_method: str) -> bool:
    normalized = _normalize_payment_method(payment_method)
    return "nequi" in normalized or "transferencia" in normalized


def payment_proof_missing(order: OrderORM) -> bool:
    return payment_requires_proof(order.payment_method) and order.payment_proof_received_at is None


async def ensure_payment_proof_status(session: AsyncSession, order: OrderORM) -> bool:
    if not payment_requires_proof(order.payment_method):
        return True
    if order.payment_proof_received_at is not None:
        return True
    proof_at = await _latest_payment_proof_at(session, order)
    if proof_at is None:
        return False
    order.payment_proof_received_at = proof_at
    await session.flush()
    return True


async def mark_payment_proof_received_for_chat(
    session: AsyncSession,
    settings: Settings,
    chat_id: int,
    received_at: datetime,
) -> int:
    result = await session.execute(
        select(OrderORM)
        .options(selectinload(OrderORM.items))
        .where(
            OrderORM.chat_id == chat_id,
            OrderORM.status.in_(("PENDING", "CONFIRMED")),
            OrderORM.payment_proof_received_at.is_(None),
            OrderORM.created_at <= received_at,
        )
        .order_by(OrderORM.created_at.desc())
    )
    orders = [order for order in result.scalars().all() if payment_requires_proof(order.payment_method)]
    if not orders:
        return 0

    client = _whatsapp_client_or_none(settings)
    for order in orders:
        order.payment_proof_received_at = received_at
    if client is not None:
        try:
            sent_message = await client.send_text_message(ChatId(chat_id), PAYMENT_PROOF_RECEIVED_TEXT)
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
        except Exception:
            logger.exception("failed to send payment proof received message chat_id=%s", chat_id)
    await session.flush()
    await admin_realtime_hub.broadcast({"type": "orders.changed"})
    await admin_realtime_hub.broadcast({"type": "conversations.changed", "chatId": str(chat_id)})
    return len(orders)


async def run_payment_proof_reminder_loop(settings: Settings, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await send_due_payment_proof_reminders(settings)
        except Exception:
            logger.exception("payment proof reminder loop failed")
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=60)


async def send_due_payment_proof_reminders(settings: Settings) -> int:
    client = _whatsapp_client_or_none(settings)
    if client is None:
        return 0
    now = datetime.now(timezone.utc)
    reminder_cutoff = now - timedelta(minutes=15)
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(OrderORM)
            .where(
                OrderORM.status.in_(("PENDING", "CONFIRMED")),
                OrderORM.payment_proof_received_at.is_(None),
                OrderORM.created_at <= reminder_cutoff,
            )
            .order_by(OrderORM.created_at.asc())
            .limit(50)
        )
        orders = [
            order
            for order in result.scalars().all()
            if payment_requires_proof(order.payment_method)
            and (order.payment_proof_reminder_sent_at is None or order.payment_proof_reminder_sent_at <= reminder_cutoff)
        ]
        if not orders:
            return 0

        sent_count = 0
        for order in orders:
            if await ensure_payment_proof_status(session, order):
                continue
            try:
                sent_message = await client.send_text_message(ChatId(order.chat_id), PAYMENT_PROOF_REMINDER_TEXT)
                order.payment_proof_reminder_sent_at = now
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
                logger.exception("failed to send payment proof reminder order_id=%s", order.id)
        await session.commit()
        if sent_count:
            await admin_realtime_hub.broadcast({"type": "conversations.changed"})
        return sent_count


async def _latest_payment_proof_at(session: AsyncSession, order: OrderORM) -> datetime | None:
    result = await session.execute(
        select(TelegramMessageORM.created_at)
        .where(
            TelegramMessageORM.chat_id == order.chat_id,
            TelegramMessageORM.direction == "inbound",
            TelegramMessageORM.media_id.is_not(None),
            TelegramMessageORM.created_at >= order.created_at,
        )
        .order_by(TelegramMessageORM.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _normalize_payment_method(value: str) -> str:
    replacements = str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU")
    return value.translate(replacements).lower().strip()


def _whatsapp_client_or_none(settings: Settings) -> WhatsAppCloudClient | None:
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return None
    return WhatsAppCloudClient(settings)
