"""Conversation orchestration code. It should coordinate state transitions and delegate business work to use cases/services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.modules.cart.domain.cart_item import CartItem
from app.modules.catalog.application.ports import ProductRepository
from app.modules.catalog.domain.enums import ProductCategory
from app.modules.catalog.domain.product import Product
from app.modules.delivery.application.use_cases.calculate_delivery import CalculateDeliveryResult
from app.modules.catalog.infrastructure.seeders.catalog_data import PRODUCT_SEEDS
from app.modules.conversations.application.ports import TelegramSessionRepository
from app.modules.conversations.domain.conversation_state import ConversationState
from app.modules.conversations.domain.telegram_session import TelegramSession
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import ChatId, ProductCode, ProductName


class ConversationGraphServices(Protocol):
    async def load_or_create_session(self, chat_id: ChatId) -> TelegramSession:
        ...

    async def persist_session(self, session: TelegramSession) -> TelegramSession:
        ...

    async def persist_step(self, session: TelegramSession, step: ConversationState) -> TelegramSession:
        ...

    async def list_products_by_category(self, category: ProductCategory) -> list[Product]:
        ...

    async def find_product(self, code_or_text: str) -> Product | None:
        ...

    async def calculate_delivery(self, address: str, neighborhood: str) -> CalculateDeliveryResult:
        ...


class SeedCatalogService:
    async def list_products_by_category(self, category: ProductCategory) -> list[Product]:
        return [
            Product(
                code=ProductCode(seed.code),
                name=ProductName(seed.name),
                category=seed.category,
                price=MoneyCOP(seed.price_cop),
                is_active=seed.is_active,
                is_available=seed.is_available,
                restricted_to=seed.restricted_to,
                requires_age_verification=seed.requires_age_verification,
            )
            for seed in PRODUCT_SEEDS
            if seed.category == category and seed.is_active
        ]

    async def find_product(self, code_or_text: str) -> Product | None:
        normalized = code_or_text.strip().upper().replace(" ", "_")
        for product in await self.list_all_products():
            if product.code.value == normalized or product.name.value.upper() == code_or_text.upper():
                return product
        return None

    async def list_all_products(self) -> list[Product]:
        products: list[Product] = []
        for category in ProductCategory:
            products.extend(await self.list_products_by_category(category))
        return products


@dataclass()
class DefaultConversationGraphServices:
    sessions: TelegramSessionRepository
    products: ProductRepository | None = None
    delivery_calculator: object | None = None
    seed_catalog: SeedCatalogService = SeedCatalogService()

    async def load_or_create_session(self, chat_id: ChatId) -> TelegramSession:
        session = await self.sessions.get_by_chat_id(chat_id)
        if session is not None:
            return session
        return await self.sessions.add(TelegramSession(chat_id=chat_id))

    async def persist_session(self, session: TelegramSession) -> TelegramSession:
        return await self.sessions.save(session)

    async def persist_step(self, session: TelegramSession, step: ConversationState) -> TelegramSession:
        session.move_to(step)
        return await self.persist_session(session)

    async def list_products_by_category(self, category: ProductCategory) -> list[Product]:
        if self.products is None:
            return await self.seed_catalog.list_products_by_category(category)
        products = await self.products.list_active()
        return [product for product in products if product.category == category]

    async def find_product(self, code_or_text: str) -> Product | None:
        if self.products is None:
            return await self.seed_catalog.find_product(code_or_text)
        try:
            return await self.products.get_by_code(ProductCode(code_or_text))
        except Exception:
            return None

    async def calculate_delivery(self, address: str, neighborhood: str) -> CalculateDeliveryResult:
        if self.delivery_calculator is None:
            return CalculateDeliveryResult(found=True, delivery_price_cop=0, pricing_source="not_configured")
        return await self.delivery_calculator.execute(address=address, neighborhood=neighborhood)


def cart_item_from_product(product: Product, quantity: int) -> CartItem:
    return CartItem(
        product_code=product.code,
        product_name=product.name,
        unit_price=product.price,
        quantity=quantity,
    )
