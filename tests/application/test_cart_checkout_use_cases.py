"""Application-layer code. It defines use cases, DTOs and ports between domain and infrastructure."""

from __future__ import annotations

from datetime import date

import pytest

from app.modules.cart.application.use_cases import (
    AddProductToCart,
    AddProductToCartCommand,
    CartOperationStatus,
    ShowCart,
)
from app.modules.catalog.domain.enums import ProductCategory, ProductRestriction
from app.modules.catalog.domain.product import Product
from app.modules.conversations.domain.telegram_session import TelegramSession
from app.modules.customers.application.customer_data import CustomerData
from app.modules.customers.application.use_cases import ExtractCustomerData, ValidateCustomerData
from app.modules.delivery.application.use_cases import CalculateDelivery
from app.modules.delivery.domain.delivery_zone import DeliveryZone
from app.modules.orders.application.use_cases import (
    CheckoutStatus,
    CreateOrder,
    CreateOrderCommand,
    PrepareCheckoutSummary,
)
from app.modules.orders.domain.order import Order
from app.modules.orders.domain.enums import PaymentMethod
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import ChatId, Neighborhood, OrderId, ProductCode, ProductName


class FakeSessionRepository:
    def __init__(self) -> None:
        self.sessions: dict[int, TelegramSession] = {}

    async def get_by_chat_id(self, chat_id: ChatId) -> TelegramSession | None:
        return self.sessions.get(chat_id.value)

    async def add(self, session: TelegramSession) -> TelegramSession:
        self.sessions[session.chat_id.value] = session
        return session

    async def save(self, session: TelegramSession) -> TelegramSession:
        self.sessions[session.chat_id.value] = session
        return session


class FakeProductRepository:
    def __init__(self, products: list[Product]) -> None:
        self.products = {product.code.value: product for product in products}

    async def get_by_code(self, code: ProductCode) -> Product | None:
        return self.products.get(code.value)

    async def list_active(self) -> list[Product]:
        return list(self.products.values())

    async def add(self, product: Product) -> Product:
        self.products[product.code.value] = product
        return product


class FakeDeliveryZoneRepository:
    def __init__(self) -> None:
        self.zones = {
            "provenza": DeliveryZone(
                code="DOMICILIO_PROVENZA_DIAMANTE",
                neighborhood=Neighborhood("Provenza"),
                delivery_price=MoneyCOP(7000),
            )
        }

    async def get_by_neighborhood(self, neighborhood: Neighborhood) -> DeliveryZone | None:
        return self.zones.get(neighborhood.value.lower())

    async def list_active(self) -> list[DeliveryZone]:
        return list(self.zones.values())

    async def add(self, zone: DeliveryZone) -> DeliveryZone:
        self.zones[zone.neighborhood.value.lower()] = zone
        return zone


class FakeOrderRepository:
    def __init__(self) -> None:
        self.orders: dict[str, Order] = {}

    async def get_by_order_number(self, order_number: OrderId) -> Order | None:
        return self.orders.get(order_number.value)

    async def list_by_chat_id(self, chat_id: ChatId, limit: int = 20) -> list[Order]:
        return list(self.orders.values())[:limit]

    async def add(self, order: Order, chat_id: ChatId) -> Order:
        self.orders[order.order_id.value] = order
        return order

    async def save(self, order: Order) -> Order:
        self.orders[order.order_id.value] = order
        return order


def make_product(
    code: str = "ASADO_MEDIO",
    price_cop: int = 22300,
    restricted_to: ProductRestriction = ProductRestriction.NONE,
) -> Product:
    return Product(
        code=ProductCode(code),
        name=ProductName("1/2 Asado"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(price_cop),
        restricted_to=restricted_to,
    )


@pytest.mark.asyncio
async def test_agregar_producto_valido() -> None:
    sessions = FakeSessionRepository()
    products = FakeProductRepository([make_product()])
    use_case = AddProductToCart(sessions, products, is_holiday=lambda _: False)

    result = await use_case.execute(
        AddProductToCartCommand(1, "ASADO_MEDIO", 2, date(2026, 7, 4))
    )

    assert result.status == CartOperationStatus.OK
    assert result.total_cop == 44600
    assert result.added_item is not None
    assert result.added_item.subtotal == MoneyCOP(44600)


@pytest.mark.asyncio
async def test_cantidad_invalida() -> None:
    use_case = AddProductToCart(
        FakeSessionRepository(),
        FakeProductRepository([make_product()]),
        is_holiday=lambda _: False,
    )

    result = await use_case.execute(
        AddProductToCartCommand(1, "ASADO_MEDIO", 0, date(2026, 7, 4))
    )

    assert result.status == CartOperationStatus.INVALID_QUANTITY


@pytest.mark.asyncio
async def test_carrito_vacio() -> None:
    result = await ShowCart(FakeSessionRepository()).execute(1)

    assert result.status == CartOperationStatus.EMPTY_CART


@pytest.mark.asyncio
async def test_producto_restringido() -> None:
    product = make_product("LASAGNA_MIXTA", 20000, ProductRestriction.WEEKEND_OR_HOLIDAY)
    use_case = AddProductToCart(
        FakeSessionRepository(),
        FakeProductRepository([product]),
        is_holiday=lambda _: False,
    )

    result = await use_case.execute(
        AddProductToCartCommand(1, "LASAGNA_MIXTA", 1, date(2026, 7, 1))
    )

    assert result.status == CartOperationStatus.PRODUCT_RESTRICTED


def test_checkout_sin_datos() -> None:
    result = ValidateCustomerData().execute(CustomerData())

    assert not result.is_valid
    assert "nombre completo" in result.missing_fields
    assert "método de pago" in result.missing_fields


def test_checkout_con_datos_completos() -> None:
    data = ExtractCustomerData().execute(
        "\n".join(
            [
                "Nombre completo: Ana Perez",
                "Telefono: 3001234567",
                "Direccion: Cra 1 #2-3",
                "Barrio: Provenza",
                "Metodo de pago: Nequi",
            ]
        )
    )
    result = ValidateCustomerData().execute(data)

    assert result.is_valid
    assert data.payment_method == PaymentMethod.NEQUI


@pytest.mark.asyncio
async def test_calculo_de_domicilio() -> None:
    result = await CalculateDelivery(FakeDeliveryZoneRepository()).execute("Provenza")

    assert result.found
    assert result.delivery_price_cop == 7000


@pytest.mark.asyncio
async def test_creacion_de_pedido() -> None:
    sessions = FakeSessionRepository()
    products = FakeProductRepository([make_product()])
    await AddProductToCart(sessions, products, is_holiday=lambda _: False).execute(
        AddProductToCartCommand(1, "ASADO_MEDIO", 1, date(2026, 7, 4))
    )
    customer_data = CustomerData(
        name="Ana Perez",
        phone="3001234567",
        address="Cra 1 #2-3",
        neighborhood="Provenza",
        payment_method=PaymentMethod.CASH,
    )
    orders = FakeOrderRepository()

    result = await CreateOrder(
        sessions,
        FakeDeliveryZoneRepository(),
        orders,
    ).execute(CreateOrderCommand(1, customer_data))

    assert result.status == CheckoutStatus.OK
    assert result.order is not None
    assert result.order.subtotal == MoneyCOP(22300)
    assert result.order.total == MoneyCOP(29300)


@pytest.mark.asyncio
async def test_snapshot_de_precios() -> None:
    sessions = FakeSessionRepository()
    product = make_product(price_cop=22300)
    products = FakeProductRepository([product])
    await AddProductToCart(sessions, products, is_holiday=lambda _: False).execute(
        AddProductToCartCommand(1, "ASADO_MEDIO", 1, date(2026, 7, 4))
    )
    product.price = MoneyCOP(30000)
    customer_data = CustomerData(
        name="Ana Perez",
        phone="3001234567",
        address="Cra 1 #2-3",
        neighborhood="Provenza",
        payment_method=PaymentMethod.CASH,
    )

    result = await CreateOrder(
        sessions,
        FakeDeliveryZoneRepository(),
        FakeOrderRepository(),
    ).execute(CreateOrderCommand(1, customer_data))

    assert result.order is not None
    assert result.order.items[0].unit_price_snapshot == MoneyCOP(22300)


@pytest.mark.asyncio
async def test_checkout_no_permite_carrito_vacio() -> None:
    result = await PrepareCheckoutSummary(FakeSessionRepository()).execute(1)

    assert result.status == CheckoutStatus.EMPTY_CART

