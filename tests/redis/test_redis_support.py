"""Redis-backed read model/cache adapter. Data here must be rebuildable from PostgreSQL."""

from __future__ import annotations

import pytest

from app.modules.catalog.domain.enums import ProductCategory
from app.modules.catalog.domain.product import Product
from app.modules.catalog.infrastructure.redis_catalog_cache import CachedProductRepository
from app.modules.conversations.application.ports import ConversationMessageHandler
from app.modules.telegram.application.handle_update.use_case import (
    HandleTelegramUpdateUseCase,
    TelegramInboundMessage,
)
from app.modules.telegram.domain.telegram_message import TelegramMessage
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import ChatId, ProductCode, ProductName


class FakeTextCache:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get_text(self, key: str) -> str | None:
        return self.values.get(key)

    async def set_text(self, key: str, value: str, ttl_seconds: int) -> None:
        self.values[key] = value

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


class FakeIdempotency:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def mark_processing(self, key: str, ttl_seconds: int) -> bool:
        if key in self.values:
            return False
        self.values[key] = "processing"
        return True

    async def mark_processed(self, key: str, ttl_seconds: int) -> None:
        self.values[key] = "processed"

    async def is_processed(self, key: str) -> bool:
        return self.values.get(key) == "processed"


class FakeLock:
    def __init__(self) -> None:
        self.locked = False
        self.acquire_calls = 0

    async def acquire(self, key: str, ttl_seconds: int) -> str | None:
        self.acquire_calls += 1
        if self.locked:
            return None
        self.locked = True
        return "token"

    async def release(self, key: str, token: str) -> None:
        self.locked = False


class FakeMessageRepository:
    def __init__(self) -> None:
        self.inbound_by_update: dict[int, TelegramMessage] = {}
        self.add_calls = 0

    async def add(self, message: TelegramMessage, direction: str = "inbound") -> TelegramMessage:
        self.add_calls += 1
        if direction == "inbound":
            self.inbound_by_update[message.update_id] = message
        return message

    async def get_inbound_by_update_id(self, update_id: int) -> TelegramMessage | None:
        return self.inbound_by_update.get(update_id)

    async def list_by_chat_id(self, chat_id: ChatId, limit: int = 50) -> list[TelegramMessage]:
        return []


class FakeTelegramClient:
    async def send_text_message(self, chat_id: ChatId, text: str) -> TelegramMessage:
        return TelegramMessage(
            chat_id=chat_id,
            message_id=999,
            update_id=0,
            text_raw=text,
            text_normalized=text,
        )


class FakeConversationHandler(ConversationMessageHandler):
    def __init__(self) -> None:
        self.calls = 0
        self.last_message_text: str | None = None

    async def handle(self, message_text: str, chat_id: ChatId) -> str:
        self.calls += 1
        self.last_message_text = message_text
        return "ok"


class FakeProductRepository:
    def __init__(self) -> None:
        self.calls = 0
        self.product = Product(
            code=ProductCode("ASADO_MEDIO"),
            name=ProductName("1/2 Asado"),
            category=ProductCategory.POLLO_ASADO,
            price=MoneyCOP(22300),
        )

    async def get_by_code(self, code: ProductCode) -> Product | None:
        self.calls += 1
        return self.product if code == self.product.code else None

    async def list_active(self) -> list[Product]:
        self.calls += 1
        return [self.product]

    async def add(self, product: Product) -> Product:
        return product


def inbound(update_id: int = 1) -> TelegramInboundMessage:
    return TelegramInboundMessage(
        update_id=update_id,
        message_id=10,
        chat_id=123,
        text="menu",
        first_name=None,
        username=None,
        message_type="text",
    )


@pytest.mark.asyncio
async def test_telegram_handler_preserva_texto_crudo_con_saltos_de_linea() -> None:
    handler = FakeConversationHandler()
    use_case = HandleTelegramUpdateUseCase(
        FakeMessageRepository(),
        FakeTelegramClient(),
        handler,
        idempotency=FakeIdempotency(),
        locks=FakeLock(),
    )
    message = inbound()
    message = TelegramInboundMessage(
        update_id=message.update_id,
        message_id=message.message_id,
        chat_id=message.chat_id,
        text="wendy\n3022873946\ncra 28 a #195-33\nel manantial\nninguna\nefectivo",
        first_name=message.first_name,
        username=message.username,
        message_type=message.message_type,
    )

    await use_case.execute(message)

    assert handler.last_message_text == message.text
    assert "\n" in (handler.last_message_text or "")


@pytest.mark.asyncio
async def test_mensaje_duplicado_no_se_procesa_dos_veces() -> None:
    messages = FakeMessageRepository()
    handler = FakeConversationHandler()
    idempotency = FakeIdempotency()
    use_case = HandleTelegramUpdateUseCase(
        messages,
        FakeTelegramClient(),
        handler,
        idempotency=idempotency,
        locks=FakeLock(),
    )

    first = await use_case.execute(inbound())
    second = await use_case.execute(inbound())

    assert first.processed
    assert second.duplicated
    assert handler.calls == 1


@pytest.mark.asyncio
async def test_lock_por_chat_id() -> None:
    lock = FakeLock()
    lock.locked = True
    handler = FakeConversationHandler()
    use_case = HandleTelegramUpdateUseCase(
        FakeMessageRepository(),
        FakeTelegramClient(),
        handler,
        idempotency=FakeIdempotency(),
        locks=lock,
    )

    result = await use_case.execute(inbound())

    assert result.duplicated
    assert handler.calls == 0


@pytest.mark.asyncio
async def test_cache_miss_consulta_postgresql() -> None:
    repo = FakeProductRepository()
    cached = CachedProductRepository(repo, FakeTextCache())

    products = await cached.list_active()

    assert products[0].code == ProductCode("ASADO_MEDIO")
    assert repo.calls == 1


@pytest.mark.asyncio
async def test_cache_hit_no_consulta_postgresql() -> None:
    repo = FakeProductRepository()
    cache = FakeTextCache()
    cached = CachedProductRepository(repo, cache)

    await cached.list_active()
    await cached.list_active()

    assert repo.calls == 1
