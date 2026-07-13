"""FastAPI router for WhatsApp Cloud API webhooks."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import perf_counter, time
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.modules.catalog.application.stock_controls import OperationalAvailabilityService
from app.modules.catalog.infrastructure.redis_catalog_cache import CachedProductRepository
from app.modules.catalog.infrastructure.sqlalchemy_product_repository import (
    SqlAlchemyProductRepository,
)
from app.modules.catalog.infrastructure.sqlalchemy_stock_control_repository import (
    SqlAlchemyStockControlRepository,
)
from app.modules.conversations.application.graph_services import DefaultConversationGraphServices
from app.modules.conversations.application.langgraph_handler import (
    LangGraphConversationMessageHandler,
)
from app.modules.conversations.graph.message_factory import BotMessageFactory
from app.modules.conversations.infrastructure.redis_session_cache import (
    CachedTelegramSessionRepository,
)
from app.modules.conversations.infrastructure.sqlalchemy_session_repository import (
    SqlAlchemyTelegramSessionRepository,
)
from app.modules.delivery.application.use_cases.calculate_delivery import (
    CalculateMapBasedDelivery,
    DeliveryPricingConfig,
)
from app.modules.delivery.infrastructure.openrouteservice_distance_client import (
    OpenRouteServiceDistanceClient,
)
from app.modules.delivery.infrastructure.redis_delivery_cache import CachedDeliveryZoneRepository
from app.modules.delivery.infrastructure.sqlalchemy_delivery_zone_repository import (
    SqlAlchemyDeliveryZoneRepository,
)
from app.modules.telegram.application.handle_update import HandleTelegramUpdateUseCase
from app.modules.telegram.application.handle_update.use_case import TelegramInboundMessage
from app.modules.telegram.infrastructure.models import TelegramMessageORM
from app.modules.telegram.infrastructure.sqlalchemy_message_repository import (
    SqlAlchemyTelegramMessageRepository,
)
from app.modules.admin.realtime import admin_realtime_hub
from app.modules.orders.application.payment_proofs import (
    PAYMENT_PROOF_RECEIVED_TEXT,
    mark_payment_proof_received_for_chat,
)
from app.modules.orders.infrastructure.admin_backend_order_client import AdminBackendOrderClient
from app.modules.orders.infrastructure.models import OrderORM
from app.modules.orders.infrastructure.sqlalchemy_order_repository import SqlAlchemyOrderRepository
from app.modules.whatsapp.api.schemas import WhatsAppWebhookPayload
from app.modules.whatsapp.infrastructure.admin_backend_message_client import (
    AdminBackendMessageClient,
)
from app.modules.whatsapp.infrastructure.media_cache import fetch_and_cache_whatsapp_media
from app.modules.whatsapp.infrastructure.whatsapp_cloud_client import WhatsAppCloudClient
from app.shared.infrastructure.database.session import get_async_session
from app.shared.infrastructure.redis.cache import RedisTextCache
from app.shared.infrastructure.redis.idempotency import RedisIdempotency
from app.shared.infrastructure.redis.locks import RedisLock
from app.shared.domain.value_object import ChatId
from app.shared.utils.text_normalizer import normalize_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["whatsapp"])

@router.get("/whatsapp", response_class=PlainTextResponse)
async def verify_whatsapp_webhook(
    settings: Annotated[Settings, Depends(get_settings)],
    mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> str:
    if mode == "subscribe" and verify_token == settings.whatsapp_verify_token and challenge:
        return challenge
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="invalid whatsapp verify token",
    )


@router.post("/whatsapp", status_code=status.HTTP_200_OK)
async def whatsapp_webhook(
    payload: WhatsAppWebhookPayload,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    started_at = perf_counter()
    inbound_messages = payload.iter_text_messages()
    inbound_media_messages = payload.iter_media_messages()
    inbound_call_events = payload.iter_call_events()
    if not inbound_messages and not inbound_media_messages and not inbound_call_events:
        return {"ok": True, "processed": False, "reason": "unsupported_update"}

    redis_cache = RedisTextCache(settings)
    idempotency = RedisIdempotency(redis_cache)
    message_repository = SqlAlchemyTelegramMessageRepository(session)
    message_client = AdminBackendMessageClient(settings)

    processed = 0
    duplicated = 0
    failed = 0
    ignored = 0

    for inbound_call in inbound_call_events:
        try:
            if await _answer_whatsapp_call_event(session, settings, idempotency, inbound_call):
                processed += 1
            else:
                duplicated += 1
        except Exception:
            failed += 1
            await session.rollback()
            logger.exception("failed to answer whatsapp call event")

    if inbound_call_events:
        await session.commit()

    if inbound_call_events and not inbound_messages and not inbound_media_messages:
        if processed:
            await admin_realtime_hub.broadcast({"type": "conversations.changed"})
        logger.info(
            "completed whatsapp webhook call_events=%s processed=%s duplicated=%s failed=%s ignored=%s duration_ms=%s",
            len(inbound_call_events),
            processed,
            duplicated,
            failed,
            ignored,
            round((perf_counter() - started_at) * 1000, 2),
        )
        return {
            "ok": True,
            "processed": processed,
            "duplicated": duplicated,
            "failed": failed,
            "ignored": ignored,
        }

    for inbound_media in inbound_media_messages:
        idempotency_key = f"telegram:update:{inbound_media.update_id}:message:{inbound_media.message_id}"
        try:
            if await idempotency.is_processed(idempotency_key):
                duplicated += 1
                continue
            if not await idempotency.mark_processing(idempotency_key, 86_400):
                duplicated += 1
                continue
            existing = await session.execute(
                select(TelegramMessageORM).where(
                    TelegramMessageORM.update_id == inbound_media.update_id,
                    TelegramMessageORM.direction == "inbound",
                )
            )
            if existing.scalar_one_or_none() is not None:
                duplicated += 1
                await idempotency.mark_processed(idempotency_key, 86_400)
                continue
            media_text = inbound_media.caption or (
                "Audio recibido" if inbound_media.media_type == "audio" else "Imagen recibida"
            )
            session.add(
                TelegramMessageORM(
                    update_id=inbound_media.update_id,
                    chat_id=inbound_media.chat_id,
                    direction="inbound",
                    message_text=media_text,
                    normalized_message_text=normalize_text(media_text),
                    message_type=inbound_media.media_type,
                    telegram_message_id=inbound_media.message_id,
                    created_at=_message_datetime(inbound_media.sent_at_epoch),
                    media_id=inbound_media.media_id,
                    media_type=inbound_media.media_type,
                    media_mime_type=inbound_media.mime_type,
                    media_sha256=inbound_media.sha256,
                )
            )
            await session.flush()
            await idempotency.mark_processed(idempotency_key, 86_400)
            payment_proof_count = await mark_payment_proof_received_for_chat(
                session,
                settings,
                inbound_media.chat_id,
                _message_datetime(inbound_media.sent_at_epoch),
            )
            try:
                await fetch_and_cache_whatsapp_media(settings, inbound_media.media_id)
            except Exception:
                logger.exception("failed to cache whatsapp media locally")
            try:
                media_sent_at = _message_datetime(inbound_media.sent_at_epoch)
                await message_client.record_incoming_message(
                    chat_id=str(inbound_media.chat_id),
                    phone=inbound_media.phone,
                    body=media_text,
                    external_message_id=inbound_media.external_message_id,
                    sent_at=media_sent_at.isoformat(),
                    attachment={
                        "type": inbound_media.media_type,
                        "mediaId": inbound_media.media_id,
                        "mimeType": inbound_media.mime_type,
                        "sha256": inbound_media.sha256,
                        "url": f"/api/media/whatsapp/{inbound_media.media_id}",
                    },
                )
                if payment_proof_count:
                    await message_client.record_bot_message(
                        chat_id=str(inbound_media.chat_id),
                        body=PAYMENT_PROOF_RECEIVED_TEXT,
                        external_message_id=f"bot:proof:{inbound_media.external_message_id}",
                        sent_at=datetime.now(timezone.utc).isoformat(),
                    )
            except Exception:
                logger.exception("failed to sync incoming whatsapp media to admin backend")
            if inbound_media.media_type == "audio":
                response_text = BotMessageFactory.audio_not_supported()
                try:
                    await WhatsAppCloudClient(settings).send_text_message(
                        ChatId(inbound_media.chat_id),
                        response_text,
                    )
                    await message_client.record_bot_message(
                        chat_id=str(inbound_media.chat_id),
                        body=response_text,
                        external_message_id=f"bot:{inbound_media.external_message_id}",
                        sent_at=datetime.now(timezone.utc).isoformat(),
                    )
                except Exception:
                    logger.exception("failed to answer whatsapp audio message")
            processed += 1
            logger.info(
                "stored whatsapp media chat_id=%s media_type=%s media_id=%s delivery_lag_ms=%s",
                inbound_media.chat_id,
                inbound_media.media_type,
                inbound_media.media_id,
                _delivery_lag_ms(inbound_media.sent_at_epoch),
            )
        except Exception:
            failed += 1
            await session.rollback()
            logger.exception("failed to store whatsapp inbound media")

    if inbound_media_messages:
        await session.commit()

    if not inbound_messages:
        if processed:
            await admin_realtime_hub.broadcast({"type": "conversations.changed"})
            await admin_realtime_hub.broadcast({"type": "orders.changed"})
        logger.info(
            "completed whatsapp webhook messages=%s media=%s calls=%s processed=%s duplicated=%s failed=%s ignored=%s duration_ms=%s",
            0,
            len(inbound_media_messages),
            len(inbound_call_events),
            processed,
            duplicated,
            failed,
            ignored,
            round((perf_counter() - started_at) * 1000, 2),
        )
        return {
            "ok": True,
            "processed": processed,
            "duplicated": duplicated,
            "failed": failed,
            "ignored": ignored,
        }

    session_repository = CachedTelegramSessionRepository(
        SqlAlchemyTelegramSessionRepository(session),
        redis_cache,
    )
    product_repository = CachedProductRepository(
        SqlAlchemyProductRepository(session),
        redis_cache,
    )
    delivery_repository = CachedDeliveryZoneRepository(
        SqlAlchemyDeliveryZoneRepository(session),
        redis_cache,
    )
    try:
        distance_client = OpenRouteServiceDistanceClient(settings)
    except Exception:
        distance_client = None
    delivery_calculator = CalculateMapBasedDelivery(
        delivery_repository,
        distance_client,
        DeliveryPricingConfig(
            origin_address=settings.delivery_origin_address,
            base_price_cop=settings.delivery_base_price_cop,
            price_per_km_cop=settings.delivery_price_per_km_cop,
            round_to_cop=settings.delivery_round_to_cop,
        ),
    )
    use_case = HandleTelegramUpdateUseCase(
        messages=message_repository,
        telegram_client=WhatsAppCloudClient(settings),
        conversation_handler=LangGraphConversationMessageHandler(
            DefaultConversationGraphServices(
                sessions=session_repository,
                products=product_repository,
                availability=OperationalAvailabilityService(
                    SqlAlchemyStockControlRepository(session),
                    settings,
                ),
                orders=SqlAlchemyOrderRepository(session),
                delivery_calculator=delivery_calculator,
            )
        ),
        idempotency=idempotency,
        locks=RedisLock(redis_cache),
    )
    for inbound in inbound_messages:
        message_started_at = perf_counter()
        delivery_lag_ms = _delivery_lag_ms(inbound.sent_at_epoch)
        admin_preparing_reply = await _admin_preparing_reply(session, inbound)
        if admin_preparing_reply is not None:
            try:
                if await _store_admin_preparing_reply(
                    session,
                    settings,
                    idempotency,
                    message_client,
                    inbound,
                    admin_preparing_reply,
                ):
                    processed += 1
                else:
                    duplicated += 1
            except Exception:
                failed += 1
                logger.exception("failed to store whatsapp admin preparing reply")
                await session.rollback()
            continue
        if _is_order_timing_query(inbound.text):
            try:
                if await _answer_order_timing_query(session, settings, idempotency, inbound):
                    processed += 1
                else:
                    duplicated += 1
            except Exception:
                failed += 1
                logger.exception("failed to answer whatsapp order timing query")
                await session.rollback()
            continue
        if await _should_ignore_stale_greeting(inbound, message_repository):
            ignored += 1
            await idempotency.mark_processed(
                f"telegram:update:{inbound.update_id}:message:{inbound.message_id}",
                86_400,
            )
            logger.info(
                "ignored stale whatsapp greeting chat_id=%s delivery_lag_ms=%s text=%s",
                inbound.chat_id,
                delivery_lag_ms,
                normalize_text(inbound.text),
            )
            continue
        if (
            settings.business_hours_enforced
            and not _is_business_open_now()
            and normalize_text(inbound.text) not in {"horario", "horarios"}
        ):
            try:
                if await _answer_outside_business_hours(session, settings, idempotency, message_client, inbound):
                    processed += 1
                else:
                    duplicated += 1
            except Exception:
                failed += 1
                logger.exception("failed to answer whatsapp outside business hours")
                await session.rollback()
            continue
        try:
            control = await message_client.get_conversation_control(chat_id=str(inbound.chat_id))
        except Exception:
            logger.exception("failed to load whatsapp conversation control")
            control = {"aiActive": True}
        if control.get("aiActive") is False:
            processed += 1
            continue

        try:
            result = await use_case.execute(
                TelegramInboundMessage(
                    update_id=inbound.update_id,
                    message_id=inbound.message_id,
                    chat_id=inbound.chat_id,
                    text=inbound.text,
                    first_name=inbound.first_name,
                    username=None,
                    message_type="text",
                )
            )
        except Exception:
            failed += 1
            logger.exception("failed to process whatsapp inbound message")
            await session.rollback()
            continue
        logger.info(
            "processed whatsapp message chat_id=%s processed=%s duplicated=%s duration_ms=%s delivery_lag_ms=%s",
            inbound.chat_id,
            result.processed,
            result.duplicated,
            round((perf_counter() - message_started_at) * 1000, 2),
            delivery_lag_ms,
        )
        try:
            await message_client.record_incoming_message(
                chat_id=str(inbound.chat_id),
                phone=inbound.phone,
                body=inbound.text,
                external_message_id=inbound.external_message_id,
                sent_at=_message_datetime(inbound.sent_at_epoch).isoformat(),
            )
        except Exception:
            logger.exception("failed to sync incoming whatsapp message to admin backend")
        if result.processed:
            processed += 1
            if result.response_text:
                try:
                    await message_client.record_bot_message(
                        chat_id=str(inbound.chat_id),
                        body=result.response_text,
                        external_message_id=f"bot:{inbound.external_message_id}",
                        sent_at=datetime.now(timezone.utc).isoformat(),
                    )
                except Exception:
                    logger.exception("failed to sync outgoing whatsapp message to admin backend")
        if result.duplicated:
            duplicated += 1

    await session.commit()
    if processed:
        await admin_realtime_hub.broadcast({"type": "conversations.changed"})
        if inbound_media_messages:
            await admin_realtime_hub.broadcast({"type": "orders.changed"})
    if processed or duplicated:
        await admin_realtime_hub.broadcast({"type": "orders.changed"})
    logger.info(
        "completed whatsapp webhook messages=%s media=%s calls=%s processed=%s duplicated=%s failed=%s ignored=%s duration_ms=%s",
        len(inbound_messages),
        len(inbound_media_messages),
        len(inbound_call_events),
        processed,
        duplicated,
        failed,
        ignored,
        round((perf_counter() - started_at) * 1000, 2),
    )

    return {
        "ok": True,
        "processed": processed,
        "duplicated": duplicated,
        "failed": failed,
        "ignored": ignored,
    }


def _delivery_lag_ms(sent_at_epoch: int | None) -> int | None:
    if sent_at_epoch is None:
        return None
    return max(0, round((time() - sent_at_epoch) * 1000))


def _message_datetime(sent_at_epoch: int | None) -> datetime:
    if sent_at_epoch is None:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(sent_at_epoch, tz=timezone.utc)


def _is_business_open_now() -> bool:
    now = datetime.now(ZoneInfo("America/Bogota"))
    return 10 <= now.hour < 16


async def _answer_outside_business_hours(
    session: AsyncSession,
    settings: Settings,
    idempotency: RedisIdempotency,
    message_client: AdminBackendMessageClient,
    inbound,
) -> bool:
    idempotency_key = f"telegram:update:{inbound.update_id}:message:{inbound.message_id}"
    if await idempotency.is_processed(idempotency_key):
        return False
    if not await idempotency.mark_processing(idempotency_key, 86_400):
        return False

    existing = await session.execute(
        select(TelegramMessageORM).where(
            TelegramMessageORM.update_id == inbound.update_id,
            TelegramMessageORM.direction == "inbound",
        )
    )
    if existing.scalar_one_or_none() is not None:
        await idempotency.mark_processed(idempotency_key, 86_400)
        return False

    inbound_datetime = _message_datetime(inbound.sent_at_epoch)
    session.add(
        TelegramMessageORM(
            update_id=inbound.update_id,
            chat_id=inbound.chat_id,
            direction="inbound",
            message_text=inbound.text,
            normalized_message_text=normalize_text(inbound.text),
            message_type="text",
            telegram_message_id=inbound.message_id,
            created_at=inbound_datetime,
        )
    )

    response_text = BotMessageFactory.outside_business_hours()
    sent_message = await WhatsAppCloudClient(settings).send_text_message(ChatId(inbound.chat_id), response_text)
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
    await idempotency.mark_processed(idempotency_key, 86_400)
    try:
        await message_client.record_incoming_message(
            chat_id=str(inbound.chat_id),
            phone=inbound.phone,
            body=inbound.text,
            external_message_id=inbound.external_message_id,
            sent_at=inbound_datetime.isoformat(),
        )
        await message_client.record_bot_message(
            chat_id=str(inbound.chat_id),
            body=response_text,
            external_message_id=f"bot:{inbound.external_message_id}",
            sent_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception:
        logger.exception("failed to sync whatsapp outside-hours autoresponse to admin backend")
    return True


async def _answer_whatsapp_call_event(
    session: AsyncSession,
    settings: Settings,
    idempotency: RedisIdempotency,
    inbound_call,
) -> bool:
    idempotency_key = f"whatsapp:call:{inbound_call.external_message_id}"
    if await idempotency.is_processed(idempotency_key):
        return False
    if not await idempotency.mark_processing(idempotency_key, 86_400):
        return False

    existing = await session.execute(
        select(TelegramMessageORM).where(
            TelegramMessageORM.update_id == inbound_call.update_id,
            TelegramMessageORM.direction == "inbound",
        )
    )
    if existing.scalar_one_or_none() is not None:
        await idempotency.mark_processed(idempotency_key, 86_400)
        return False

    call_text = "Llamada recibida por WhatsApp"
    session.add(
        TelegramMessageORM(
            update_id=inbound_call.update_id,
            chat_id=inbound_call.chat_id,
            direction="inbound",
            message_text=call_text,
            normalized_message_text=normalize_text(call_text),
            message_type="call",
            telegram_message_id=inbound_call.message_id,
            created_at=_message_datetime(inbound_call.sent_at_epoch),
        )
    )

    response_text = _whatsapp_call_response_text()
    sent_message = await WhatsAppCloudClient(settings).send_text_message(ChatId(inbound_call.chat_id), response_text)
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
    try:
        message_client = AdminBackendMessageClient(settings)
        await message_client.record_incoming_message(
            chat_id=str(inbound_call.chat_id),
            phone=inbound_call.phone,
            body=call_text,
            external_message_id=inbound_call.external_message_id,
        )
        await message_client.record_bot_message(
            chat_id=str(inbound_call.chat_id),
            body=response_text,
        )
    except Exception:
        logger.exception("failed to sync whatsapp call autoresponse to admin backend")
    await session.flush()
    await idempotency.mark_processed(idempotency_key, 86_400)
    logger.info(
        "answered whatsapp call event chat_id=%s status=%s",
        inbound_call.chat_id,
        inbound_call.status,
    )
    return True


def _whatsapp_call_response_text() -> str:
    return "\n\n".join(
        [
            "Gracias por comunicarte con ASADERO MC CHICKEN EXPRESS.",
            "En este momento no estamos recibiendo llamadas por WhatsApp, pero con gusto te atendemos por este chat.",
            "Puedes escribir tu pedido directamente o elegir una opcion:",
            "\n".join(
                [
                    "1. Pedir por menu 📋",
                    "2. Pedir escribiendo ✍️",
                    "3. Ver carrito 🧾",
                    "4. Horarios 🕒",
                ]
            ),
        ]
    )


async def _admin_preparing_reply(session: AsyncSession, inbound) -> tuple[str, int | None] | None:
    if inbound.button_reply_id:
        button_reply = _admin_preparing_button_reply(inbound.button_reply_id)
        if button_reply is not None:
            reply_value, order_id = button_reply
            if order_id is not None:
                return button_reply
            recent_order_id = await _recent_admin_preparing_prompt_order_id(session, inbound.chat_id)
            if recent_order_id is not None:
                return reply_value, recent_order_id
            return None
    reply = _yes_no_reply_from_text(inbound.text)
    if reply is None:
        return None
    order_id = await _recent_admin_preparing_prompt_order_id(session, inbound.chat_id)
    if order_id is not None:
        return reply, order_id
    return None


def _admin_preparing_button_reply(button_reply_id: str) -> tuple[str, int | None] | None:
    if button_reply_id.startswith("admin_preparing_yes"):
        return "yes", _button_order_id(button_reply_id)
    if button_reply_id.startswith("admin_preparing_no"):
        return "no", _button_order_id(button_reply_id)
    return None


def _button_order_id(button_reply_id: str) -> int | None:
    _, separator, raw_order_id = button_reply_id.partition(":")
    if not separator or not raw_order_id.isdigit():
        return None
    return int(raw_order_id)


async def _store_admin_preparing_reply(
    session: AsyncSession,
    settings: Settings,
    idempotency: RedisIdempotency,
    message_client: AdminBackendMessageClient,
    inbound,
    admin_preparing_reply: tuple[str, int | None],
) -> bool:
    idempotency_key = f"telegram:update:{inbound.update_id}:message:{inbound.message_id}"
    if await idempotency.is_processed(idempotency_key):
        return False
    if not await idempotency.mark_processing(idempotency_key, 86_400):
        return False
    existing = await session.execute(
        select(TelegramMessageORM).where(
            TelegramMessageORM.update_id == inbound.update_id,
            TelegramMessageORM.direction == "inbound",
        )
    )
    if existing.scalar_one_or_none() is not None:
        await idempotency.mark_processed(idempotency_key, 86_400)
        return False
    inbound_text = inbound.text.strip()
    normalized_text = normalize_text(inbound_text)
    inbound_created_at = _message_datetime(inbound.sent_at_epoch)
    reply_value, order_id = admin_preparing_reply
    session.add(
        TelegramMessageORM(
            update_id=inbound.update_id,
            chat_id=inbound.chat_id,
            direction="inbound",
            message_text=inbound_text,
            normalized_message_text=normalized_text,
            message_type="admin_reply",
            telegram_message_id=inbound.message_id,
            created_at=inbound_created_at,
        )
    )
    try:
        await message_client.record_incoming_message(
            chat_id=str(inbound.chat_id),
            phone=inbound.phone,
            body=inbound_text,
            external_message_id=inbound.external_message_id,
            sent_at=inbound_created_at.isoformat(),
        )
    except Exception:
        logger.exception("failed to sync admin preparing reply to admin backend")
    if reply_value == "yes":
        await _continue_order_after_admin_yes(
            session,
            settings,
            message_client,
            inbound.chat_id,
            order_id,
            inbound.external_message_id,
        )
    elif reply_value == "no":
        await _cancel_order_after_admin_no(
            session,
            settings,
            message_client,
            inbound.chat_id,
            order_id,
            inbound.external_message_id,
        )
    await session.flush()
    await idempotency.mark_processed(idempotency_key, 86_400)
    return True


async def _recent_admin_preparing_prompt_order_id(session: AsyncSession, chat_id: int) -> int | None:
    latest_order = await _latest_order_for_chat(session, chat_id)
    if latest_order is None:
        return None
    result = await session.execute(
        select(TelegramMessageORM)
        .where(
            TelegramMessageORM.chat_id == chat_id,
            TelegramMessageORM.direction == "outbound",
            TelegramMessageORM.created_at >= latest_order.created_at,
            TelegramMessageORM.message_type.in_(("admin_text", "text")),
        )
        .order_by(TelegramMessageORM.created_at.desc())
        .limit(1)
    )
    latest_message = result.scalar_one_or_none()
    if latest_message is None:
        return None
    text = normalize_text(latest_message.message_text or "")
    if not _text_contains_admin_preparing_prompt(text):
        return None
    return latest_order.id


def _text_contains_admin_preparing_prompt(text: str) -> bool:
    normalized = normalize_text(text)
    return (
        "en este momento no contamos" in normalized
        and ("desea pedir de igual manera" in normalized or "desea pedir de alguna otra cosa" in normalized)
    )


def _yes_no_reply_from_text(text: str) -> str | None:
    normalized = normalize_text(text)
    if normalized in {"si", "sí"}:
        return "yes"
    if normalized == "no":
        return "no"
    lines = [normalize_text(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    if lines:
        last_line = lines[-1]
        if last_line in {"si", "sí"}:
            return "yes"
        if last_line == "no":
            return "no"
    words = normalized.split()
    if words:
        if words[-1] in {"si", "sí"}:
            return "yes"
        if words[-1] == "no":
            return "no"
    return None


async def _cancel_order_after_admin_no(
    session: AsyncSession,
    settings: Settings,
    message_client: AdminBackendMessageClient,
    chat_id: int,
    order_id: int | None,
    inbound_external_message_id: str,
) -> None:
    order = await _order_for_admin_reply(session, chat_id, order_id)
    if order is None or (order.status or "").upper() == "CANCELLED":
        return
    order.status = "CANCELLED"
    response_text = (
        "Entendido, ya cancelamos tu pedido. Muchas gracias por pedir en ASADERO MC CHICKEN EXPRESS. "
        "Quedamos atentos para ayudarte con cualquier otro pedido cuando lo desees."
    )
    sent_message = await WhatsAppCloudClient(settings).send_text_message(ChatId(chat_id), response_text)
    session.add(
        TelegramMessageORM(
            update_id=0,
            chat_id=sent_message.chat_id.value,
            direction="outbound",
            message_text=sent_message.text_raw,
            normalized_message_text=sent_message.text_normalized,
            message_type="admin_text",
            telegram_message_id=sent_message.message_id,
            created_at=sent_message.received_at,
        )
    )
    await _sync_admin_order_status(settings, order, "CANCELLED", "Cliente no acepto el cambio sugerido")
    await _sync_admin_bot_message(message_client, chat_id, response_text, f"bot:admin-preparing-no:{inbound_external_message_id}")


async def _continue_order_after_admin_yes(
    session: AsyncSession,
    settings: Settings,
    message_client: AdminBackendMessageClient,
    chat_id: int,
    order_id: int | None,
    inbound_external_message_id: str,
) -> None:
    order = await _order_for_admin_reply(session, chat_id, order_id)
    if order is None:
        return
    if (order.status or "").upper() != "PREPARING":
        order.status = "PREPARING"
        order.accepted_at = datetime.now(timezone.utc)
    response_text = (
        "Perfecto, muchas gracias por confirmarnos. Tu pedido ya esta en preparacion. "
        "En este estado normalmente tarda entre 25 y 30 minutos. Apenas este listo te avisamos."
    )
    sent_message = await WhatsAppCloudClient(settings).send_text_message(ChatId(chat_id), response_text)
    session.add(
        TelegramMessageORM(
            update_id=0,
            chat_id=sent_message.chat_id.value,
            direction="outbound",
            message_text=sent_message.text_raw,
            normalized_message_text=sent_message.text_normalized,
            message_type="admin_text",
            telegram_message_id=sent_message.message_id,
            created_at=sent_message.received_at,
        )
    )
    await _sync_admin_order_status(settings, order, "PREPARING")
    await _sync_admin_bot_message(message_client, chat_id, response_text, f"bot:admin-preparing-yes:{inbound_external_message_id}")


async def _sync_admin_order_status(
    settings: Settings,
    order: OrderORM,
    status_value: str,
    reason: str | None = None,
) -> None:
    try:
        await AdminBackendOrderClient(settings).update_order_status(
            external_bot_id=order.order_number,
            status=status_value,
            reason=reason,
        )
    except Exception:
        logger.exception("failed to sync admin order status after preparing reply")


async def _sync_admin_bot_message(
    message_client: AdminBackendMessageClient,
    chat_id: int,
    response_text: str,
    external_message_id: str,
) -> None:
    try:
        await message_client.record_bot_message(
            chat_id=str(chat_id),
            body=response_text,
            external_message_id=external_message_id,
            sent_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception:
        logger.exception("failed to sync admin preparing bot response to admin backend")


async def _order_for_admin_reply(session: AsyncSession, chat_id: int, order_id: int | None) -> OrderORM | None:
    if order_id is not None:
        result = await session.execute(
            select(OrderORM).where(
                OrderORM.id == order_id,
                OrderORM.chat_id == chat_id,
            )
        )
        return result.scalar_one_or_none()
    return await _latest_order_for_chat(session, chat_id)


async def _latest_order_for_chat(session: AsyncSession, chat_id: int) -> OrderORM | None:
    result = await session.execute(
        select(OrderORM)
        .where(OrderORM.chat_id == chat_id)
        .order_by(OrderORM.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _answer_order_timing_query(
    session: AsyncSession,
    settings: Settings,
    idempotency: RedisIdempotency,
    inbound,
) -> bool:
    idempotency_key = f"telegram:update:{inbound.update_id}:message:{inbound.message_id}"
    if await idempotency.is_processed(idempotency_key):
        return False
    if not await idempotency.mark_processing(idempotency_key, 86_400):
        return False
    existing = await session.execute(
        select(TelegramMessageORM).where(
            TelegramMessageORM.update_id == inbound.update_id,
            TelegramMessageORM.direction == "inbound",
        )
    )
    if existing.scalar_one_or_none() is not None:
        await idempotency.mark_processed(idempotency_key, 86_400)
        return False

    inbound_row = TelegramMessageORM(
        update_id=inbound.update_id,
        chat_id=inbound.chat_id,
        direction="inbound",
        message_text=inbound.text,
        normalized_message_text=normalize_text(inbound.text),
        message_type="text",
        telegram_message_id=inbound.message_id,
        created_at=_message_datetime(inbound.sent_at_epoch),
    )
    session.add(inbound_row)
    response_text = await _order_timing_answer(session, inbound.chat_id)
    sent_message = await WhatsAppCloudClient(settings).send_text_message(ChatId(inbound.chat_id), response_text)
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
    await session.flush()
    await idempotency.mark_processed(idempotency_key, 86_400)
    return True


async def _order_timing_answer(session: AsyncSession, chat_id: int) -> str:
    result = await session.execute(
        select(OrderORM)
        .where(OrderORM.chat_id == chat_id)
        .order_by(OrderORM.created_at.desc())
        .limit(1)
    )
    order = result.scalar_one_or_none()
    if order is None:
        return (
            "Con gusto te ayudo. En este momento no encuentro un pedido reciente asociado a este chat. "
            "Si ya realizaste el pedido, por favor espera un momento o escribenos el numero del pedido para revisarlo."
        )
    status_value = (order.status or "").upper()
    if status_value in {"PENDING", "CONFIRMED"}:
        return (
            "👋 Claro, tu pedido ya fue recibido. "
            "En este estado el tiempo estimado es de aproximadamente 40 minutos. "
            "Estamos atentos para prepararlo lo mas pronto posible. Gracias por tu paciencia 🙌"
        )
    if status_value == "PREPARING":
        return (
            "🍗 Tu pedido ya esta en preparacion. "
            "Normalmente puede tardar entre 25 y 30 minutos. "
            "Apenas este listo te avisamos. Gracias por esperar 🙌"
        )
    if status_value in {"DELIVERED", "DISPATCHED", "DESPACHADO"}:
        return (
            "🛵 Tu pedido ya fue despachado. "
            "El tiempo estimado de llegada es de 10 a 15 minutos, dependiendo de la ruta. "
            "Gracias por tu paciencia 🙌"
        )
    if status_value == "CANCELLED":
        return (
            "Tu pedido aparece como cancelado en nuestro sistema. "
            "Si necesitas hacer uno nuevo, con gusto te ayudamos."
        )
    return (
        "Estamos revisando el estado de tu pedido. "
        "Te confirmamos lo antes posible, gracias por tu paciencia 🙌"
    )


def _is_order_timing_query(text: str) -> bool:
    normalized = normalize_text(text)
    if _looks_like_new_order_request(normalized):
        return False
    timing_terms = (
        "demora",
        "demorar",
        "demorado",
        "tarda",
        "tardar",
        "cuanto falta",
        "cuánto falta",
        "cuando llega",
        "cuándo llega",
        "llega",
        "llegar",
        "como va",
        "cómo va",
        "estado",
        "despacho",
        "despachado",
    )
    order_terms = ("pedido", "domicilio", "orden", "pollo", "comida")
    direct_time_question = any(
        phrase in normalized
        for phrase in (
            "cuanto se demora",
            "cuanto demora",
            "cuanto tarda",
            "cuánto se demora",
            "cuánto demora",
            "cuánto tarda",
            "cuando llega",
            "cuándo llega",
        )
    )
    return direct_time_question or (
        any(term in normalized for term in timing_terms) and any(term in normalized for term in order_terms)
    )


def _looks_like_new_order_request(normalized: str) -> bool:
    return any(
        phrase in normalized
        for phrase in (
            "otro pedido",
            "nuevo pedido",
            "hacer pedido",
            "hacer otro pedido",
            "hacer un pedido",
            "pedir otra vez",
            "pedir de nuevo",
            "quiero pedir",
            "quiero ordenar",
            "quiero comprar",
        )
    )


async def _should_ignore_stale_greeting(
    inbound,
    message_repository: SqlAlchemyTelegramMessageRepository,
) -> bool:
    normalized = normalize_text(inbound.text)
    if normalized not in {"hola", "buenas", "buenos dias", "buenos días", "buenas tardes", "buenas noches"}:
        return False
    if inbound.sent_at_epoch is None:
        return False
    sent_at = datetime.fromtimestamp(inbound.sent_at_epoch, tz=timezone.utc)
    recent_messages = await message_repository.list_by_chat_id(ChatId(inbound.chat_id), limit=8)
    latest_outbound = next(
        (message for message in recent_messages if message.update_id == 0),
        None,
    )
    return latest_outbound is not None and latest_outbound.received_at > sent_at
