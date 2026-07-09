"""Conversation orchestration code. It should coordinate state transitions and delegate business work to use cases/services."""

from __future__ import annotations

import json

from app.modules.conversations.application.ports import TelegramSessionRepository
from app.modules.conversations.domain.conversation_state import ConversationState
from app.modules.conversations.domain.telegram_session import TelegramSession
from app.modules.conversations.infrastructure.mappers import cart_item_from_json, cart_item_to_json
from app.shared.application.redis_ports import RedisCachePort
from app.shared.domain.value_object import ChatId, ProductCode


class CachedTelegramSessionRepository:
    def __init__(
        self,
        wrapped: TelegramSessionRepository,
        cache: RedisCachePort,
        ttl_seconds: int = 600,
    ) -> None:
        self._wrapped = wrapped
        self._cache = cache
        self._ttl_seconds = ttl_seconds

    async def get_by_chat_id(self, chat_id: ChatId) -> TelegramSession | None:
        key = self._key(chat_id)
        cached = await self._cache.get_text(key)
        if cached:
            return _session_from_dict(json.loads(cached))
        session = await self._wrapped.get_by_chat_id(chat_id)
        if session is not None:
            await self._cache.set_text(key, json.dumps(_session_to_dict(session)), self._ttl_seconds)
        return session

    async def add(self, session: TelegramSession) -> TelegramSession:
        saved = await self._wrapped.add(session)
        await self._cache.set_text(
            self._key(saved.chat_id),
            json.dumps(_session_to_dict(saved)),
            self._ttl_seconds,
        )
        return saved

    async def save(self, session: TelegramSession) -> TelegramSession:
        saved = await self._wrapped.save(session)
        await self._cache.set_text(
            self._key(saved.chat_id),
            json.dumps(_session_to_dict(saved)),
            self._ttl_seconds,
        )
        return saved

    def _key(self, chat_id: ChatId) -> str:
        return f"conversation:session:{chat_id.value}"


def _session_to_dict(session: TelegramSession) -> dict[str, object]:
    return {
        "chat_id": session.chat_id.value,
        "current_step": session.current_step.value,
        "selected_product_code": (
            session.selected_product_code.value if session.selected_product_code else None
        ),
        "selected_chicken_part": session.selected_chicken_part,
        "cart": [cart_item_to_json(item) for item in session.cart],
        "customer_name": session.customer_name,
        "customer_phone": session.customer_phone,
        "customer_address": session.customer_address,
        "customer_neighborhood": session.customer_neighborhood,
        "payment_method": session.payment_method,
        "observations": session.observations,
    }


def _session_from_dict(data: dict[str, object]) -> TelegramSession:
    selected = data.get("selected_product_code")
    return TelegramSession(
        chat_id=ChatId(int(data["chat_id"])),
        current_step=ConversationState(str(data["current_step"])),
        selected_product_code=ProductCode(str(selected)) if selected else None,
        selected_chicken_part=data.get("selected_chicken_part") or None,
        cart=[cart_item_from_json(item) for item in data.get("cart", [])],
        customer_name=data.get("customer_name") or None,
        customer_phone=data.get("customer_phone") or None,
        customer_address=data.get("customer_address") or None,
        customer_neighborhood=data.get("customer_neighborhood") or None,
        payment_method=data.get("payment_method") or None,
        observations=data.get("observations") or None,
    )
