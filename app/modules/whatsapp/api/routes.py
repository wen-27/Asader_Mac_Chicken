"""FastAPI router for WhatsApp Cloud API webhooks."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.modules.catalog.infrastructure.redis_catalog_cache import CachedProductRepository
from app.modules.catalog.infrastructure.sqlalchemy_product_repository import (
    SqlAlchemyProductRepository,
)
from app.modules.conversations.application.graph_services import DefaultConversationGraphServices
from app.modules.conversations.application.langgraph_handler import (
    LangGraphConversationMessageHandler,
)
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
from app.modules.telegram.infrastructure.sqlalchemy_message_repository import (
    SqlAlchemyTelegramMessageRepository,
)
from app.modules.whatsapp.api.schemas import WhatsAppWebhookPayload
from app.modules.whatsapp.infrastructure.admin_backend_message_client import (
    AdminBackendMessageClient,
)
from app.modules.whatsapp.infrastructure.whatsapp_cloud_client import WhatsAppCloudClient
from app.shared.infrastructure.database.session import get_async_session
from app.shared.infrastructure.redis.cache import RedisTextCache
from app.shared.infrastructure.redis.idempotency import RedisIdempotency
from app.shared.infrastructure.redis.locks import RedisLock

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
    inbound_messages = payload.iter_text_messages()
    if not inbound_messages:
        return {"ok": True, "processed": False, "reason": "unsupported_update"}

    redis_cache = RedisTextCache(settings)
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
        messages=SqlAlchemyTelegramMessageRepository(session),
        telegram_client=WhatsAppCloudClient(settings),
        conversation_handler=LangGraphConversationMessageHandler(
            DefaultConversationGraphServices(
                sessions=session_repository,
                products=product_repository,
                delivery_calculator=delivery_calculator,
            )
        ),
        idempotency=RedisIdempotency(redis_cache),
        locks=RedisLock(redis_cache),
    )
    message_client = AdminBackendMessageClient(settings)

    processed = 0
    duplicated = 0
    for inbound in inbound_messages:
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
        if result.processed:
            processed += 1
            try:
                await message_client.record_incoming_message(
                    chat_id=str(inbound.chat_id),
                    phone=inbound.phone,
                    body=inbound.text,
                    external_message_id=inbound.external_message_id,
                )
            except Exception:
                logger.exception("failed to sync incoming whatsapp message to admin backend")
        if result.duplicated:
            duplicated += 1

    await session.commit()

    return {
        "ok": True,
        "processed": processed,
        "duplicated": duplicated,
    }
