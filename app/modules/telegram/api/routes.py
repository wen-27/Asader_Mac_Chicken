"""FastAPI router for this module. Keep controllers thin and delegate real work to application services."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings, get_settings
from app.modules.catalog.infrastructure.sqlalchemy_product_repository import (
    SqlAlchemyProductRepository,
)
from app.modules.catalog.infrastructure.redis_catalog_cache import CachedProductRepository
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
from app.modules.telegram.api.schemas import TelegramUpdateSchema
from app.modules.telegram.application.handle_update import HandleTelegramUpdateUseCase
from app.modules.telegram.application.handle_update.use_case import TelegramInboundMessage
from app.modules.telegram.infrastructure.sqlalchemy_message_repository import (
    SqlAlchemyTelegramMessageRepository,
)
from app.modules.telegram.infrastructure.telegram_http_client import TelegramHttpClient
from app.shared.infrastructure.database.session import get_async_session
from app.shared.infrastructure.redis.cache import RedisTextCache
from app.shared.infrastructure.redis.idempotency import RedisIdempotency
from app.shared.infrastructure.redis.locks import RedisLock

router = APIRouter(prefix="/webhooks", tags=["telegram"])


def validate_telegram_secret(
    settings: Annotated[Settings, Depends(get_settings)],
    secret_token: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
) -> None:
    if settings.telegram_webhook_secret and secret_token != settings.telegram_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid telegram webhook secret",
        )


@router.post("/telegram", status_code=status.HTTP_200_OK)
async def telegram_webhook(
    update: TelegramUpdateSchema,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[None, Depends(validate_telegram_secret)],
) -> dict[str, object]:
    if update.message is None:
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
        telegram_client=TelegramHttpClient(settings),
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
    result = await use_case.execute(
        TelegramInboundMessage(
            update_id=update.update_id,
            message_id=update.message_id,
            chat_id=update.chat_id,
            text=update.text,
            first_name=update.first_name,
            username=update.username,
            message_type=update.message_type,
        )
    )
    await session.commit()

    return {
        "ok": True,
        "processed": result.processed,
        "duplicated": result.duplicated,
    }
