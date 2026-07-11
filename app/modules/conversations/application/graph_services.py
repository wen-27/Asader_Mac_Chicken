"""Conversation orchestration code. It should coordinate state transitions and delegate business work to use cases/services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.config.settings import get_settings
from app.modules.cart.domain.cart_item import CartItem
from app.modules.catalog.application.ports import ProductRepository
from app.modules.catalog.domain.enums import ProductCategory
from app.modules.catalog.domain.product import Product
from app.modules.delivery.application.use_cases.calculate_delivery import CalculateDeliveryResult
from app.modules.catalog.infrastructure.seeders.catalog_data import PRODUCT_SEEDS
from app.modules.conversations.application.ports import TelegramSessionRepository
from app.modules.conversations.domain.conversation_state import ConversationState
from app.modules.conversations.domain.telegram_session import TelegramSession
from app.modules.customers.domain.customer import Customer
from app.modules.delivery.domain.delivery_zone import DeliveryZone
from app.modules.orders.application.ports import OrderRepository
from app.modules.orders.domain.enums import OrderStatus, PaymentMethod
from app.modules.orders.domain.order import Order
from app.modules.orders.domain.order_item import OrderItem
from app.modules.orders.infrastructure.admin_backend_order_client import (
    AdminOrderCustomerPayload,
    AdminOrderItemPayload,
    AdminOrderPayload,
    AdminBackendOrderClient,
)
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import Address, ChatId, CustomerName, Neighborhood, OrderId, PhoneNumber, ProductCode, ProductName


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

    async def sync_confirmed_order(self, payload: AdminOrderPayload) -> None:
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
    orders: OrderRepository | None = None
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

    async def sync_confirmed_order(self, payload: AdminOrderPayload) -> None:
        if self.orders is not None:
            await self.orders.add(_order_from_admin_payload(payload), ChatId(int(payload.chat_id)))
            return
        await AdminBackendOrderClient(get_settings()).sync_order_payload(payload)


def cart_item_from_product(product: Product, quantity: int) -> CartItem:
    return CartItem(
        product_code=product.code,
        product_name=product.name,
        unit_price=product.price,
        quantity=quantity,
    )


def _order_from_admin_payload(payload: AdminOrderPayload) -> Order:
    address, neighborhood = _split_customer_address(payload.customer.address)
    order = Order(
        order_id=OrderId(payload.external_bot_id),
        customer=Customer(
            name=CustomerName(payload.customer.full_name),
            phone=PhoneNumber(payload.customer.phone),
            address=Address(address),
            neighborhood=Neighborhood(neighborhood),
            observations=payload.observations or "Ninguna",
        ),
        items=[
            OrderItem(
                product_code=ProductCode(item.product_code),
                product_name=ProductName(item.product_name),
                unit_price_snapshot=MoneyCOP(item.unit_price_cop),
                quantity=item.quantity,
                subtotal_snapshot=MoneyCOP(item.unit_price_cop * item.quantity),
            )
            for item in payload.items
        ],
        delivery_zone=DeliveryZone(
            code="WHATSAPP_CHECKOUT",
            neighborhood=Neighborhood(neighborhood),
            delivery_price=MoneyCOP(payload.delivery_fee_cop),
            is_active=True,
        ),
        payment_method=_payment_method_from_text(payload.payment_method),
        status=OrderStatus.CONFIRMED,
    )
    return order


def _split_customer_address(raw_address: str) -> tuple[str, str]:
    parts = [part.strip() for part in raw_address.split(" - ", 1)]
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0], parts[1]
    return raw_address.strip(), "Sin barrio"


def _payment_method_from_text(value: str) -> PaymentMethod:
    normalized = value.strip().lower()
    for method in PaymentMethod:
        if normalized == method.value.lower():
            return method
    if "nequi" in normalized:
        return PaymentMethod.NEQUI
    if "datafono" in normalized or "datáfono" in normalized:
        return PaymentMethod.DATAPHONE
    if "bancolombia" in normalized or "transferencia" in normalized:
        return PaymentMethod.BANCOLOMBIA_TRANSFER
    return PaymentMethod.CASH
