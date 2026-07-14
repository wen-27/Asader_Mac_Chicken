"""Conversation orchestration code. It should coordinate state transitions and delegate business work to use cases/services."""

from __future__ import annotations

from datetime import date

import pytest

from app.modules.catalog.domain.enums import ProductCategory, ProductRestriction
from app.modules.catalog.domain.product import Product
from app.modules.conversations.domain.conversation_state import ConversationState
from app.modules.conversations.domain.intent import ConversationIntent
from app.modules.conversations.domain.telegram_session import TelegramSession
from app.modules.conversations.application.graph_services import AdminOrderPayload, cart_item_from_product
from app.modules.conversations.graph.graph import build_conversation_graph
from app.modules.conversations.graph import nodes
from app.modules.conversations.graph.router import route_after_customer_validation, route_after_intent
from app.modules.conversations.graph.state import CartLineState, ConversationGraphState
from app.modules.delivery.application.use_cases.calculate_delivery import CalculateDeliveryResult
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import ChatId, ProductCode, ProductName


class FakeConversationServices:
    def __init__(self) -> None:
        self.session = TelegramSession(chat_id=ChatId(123))
        self.persisted_steps: list[ConversationState] = []
        self.synced_orders: list[AdminOrderPayload] = []
        self.fail_sync = False
        self.soup_available = True
        self.created_orders: list[str] = []
        self.products = {
            "JUGO_HIT_PERSONAL": Product(
                code=ProductCode("JUGO_HIT_PERSONAL"),
                name=ProductName("Jugos Hit personal"),
                category=ProductCategory.BEBIDAS,
                price=MoneyCOP(3000),
            ),
            "PERSONAL_400": Product(
                code=ProductCode("PERSONAL_400"),
                name=ProductName("Coca-Cola personal 400 ml"),
                category=ProductCategory.BEBIDAS,
                price=MoneyCOP(3500),
            ),
            "GASEOSA_25": Product(
                code=ProductCode("GASEOSA_25"),
                name=ProductName("Gaseosa 2.5 L"),
                category=ProductCategory.BEBIDAS,
                price=MoneyCOP(8500),
            ),
            "AGUA_BOTELLA": Product(
                code=ProductCode("AGUA_BOTELLA"),
                name=ProductName("Agua botella"),
                category=ProductCategory.BEBIDAS,
                price=MoneyCOP(2600),
            ),
            "ASADO_MEDIO": Product(
                code=ProductCode("ASADO_MEDIO"),
                name=ProductName("1/2 Asado"),
                category=ProductCategory.POLLO_ASADO,
                price=MoneyCOP(22300),
            ),
            "ASADO_CUARTO": Product(
                code=ProductCode("ASADO_CUARTO"),
                name=ProductName("1/4 Asado"),
                category=ProductCategory.POLLO_ASADO,
                price=MoneyCOP(11800),
            ),
            "ASADO_34": Product(
                code=ProductCode("ASADO_34"),
                name=ProductName("3/4 Asado"),
                category=ProductCategory.POLLO_ASADO,
                price=MoneyCOP(33300),
            ),
            "BROASTER_MEDIO": Product(
                code=ProductCode("BROASTER_MEDIO"),
                name=ProductName("1/2 Broasted"),
                category=ProductCategory.POLLO_BROASTER,
                price=MoneyCOP(25500),
            ),
            "BROASTER_ENTERO": Product(
                code=ProductCode("BROASTER_ENTERO"),
                name=ProductName("Broasted Entero"),
                category=ProductCategory.POLLO_BROASTER,
                price=MoneyCOP(51000),
            ),
            "BROASTER_CUARTO": Product(
                code=ProductCode("BROASTER_CUARTO"),
                name=ProductName("1/4 Broasted"),
                category=ProductCategory.POLLO_BROASTER,
                price=MoneyCOP(13500),
            ),
            "BROASTER_34": Product(
                code=ProductCode("BROASTER_34"),
                name=ProductName("3/4 Broasted"),
                category=ProductCategory.POLLO_BROASTER,
                price=MoneyCOP(38200),
            ),
            "LASAGNA_MIXTA": Product(
                code=ProductCode("LASAGNA_MIXTA"),
                name=ProductName("Lasagna Mixta"),
                category=ProductCategory.ESPECIALES,
                price=MoneyCOP(20000),
                restricted_to=ProductRestriction.WEEKEND_OR_HOLIDAY,
            ),
            "MADURO_QUESO": Product(
                code=ProductCode("MADURO_QUESO"),
                name=ProductName("Maduro con Queso"),
                category=ProductCategory.ESPECIALES,
                price=MoneyCOP(9500),
                restricted_to=ProductRestriction.WEEKEND_OR_HOLIDAY,
            ),
            "PAPA_SALADA": Product(
                code=ProductCode("PAPA_SALADA"),
                name=ProductName("Papa o yuca salada"),
                category=ProductCategory.ADICIONALES,
                price=MoneyCOP(5000),
            ),
            "YUCA_FRITA": Product(
                code=ProductCode("YUCA_FRITA"),
                name=ProductName("Yuca frita"),
                category=ProductCategory.ADICIONALES,
                price=MoneyCOP(5000),
            ),
            "ADICIONAL_SALSAS": Product(
                code=ProductCode("ADICIONAL_SALSAS"),
                name=ProductName("Adicional de Salsas"),
                category=ProductCategory.ADICIONALES,
                price=MoneyCOP(900),
            ),
        }

    async def load_or_create_session(self, chat_id: ChatId) -> TelegramSession:
        return self.session

    async def persist_session(self, session: TelegramSession) -> TelegramSession:
        self.session = session
        self.persisted_steps.append(session.current_step)
        return session

    async def persist_step(
        self,
        session: TelegramSession,
        step: ConversationState,
    ) -> TelegramSession:
        session.move_to(step)
        return await self.persist_session(session)

    async def list_products_by_category(self, category: ProductCategory) -> list[Product]:
        return [product for product in self.products.values() if product.category == category]

    async def find_product(self, code_or_text: str) -> Product | None:
        code = code_or_text.upper().replace(" ", "_")
        return self.products.get(code)

    async def calculate_delivery(self, address: str, neighborhood: str) -> CalculateDeliveryResult:
        return CalculateDeliveryResult(
            found=True,
            delivery_price_cop=2000,
            distance_km=0.0,
            pricing_source="test",
        )

    async def soup_is_available(self) -> bool:
        return self.soup_available

    async def sync_confirmed_order(self, payload: AdminOrderPayload) -> None:
        if self.fail_sync:
            raise RuntimeError("admin backend unavailable")
        self.synced_orders.append(payload)

    async def create_confirmed_order(self, chat_id: ChatId, delivery_price_cop: int) -> str | None:
        order_number = f"TEST-{chat_id.value}-{len(self.created_orders) + 1}"
        self.created_orders.append(order_number)
        return order_number


@pytest.mark.asyncio
async def test_menu_intent_transitions_to_main_menu() -> None:
    services = FakeConversationServices()
    state = ConversationGraphState(chat_id=123, raw_text="menu")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    assert route_after_intent(state) == "show_main_menu"

    state = await nodes.show_main_menu(state, services)

    assert state.current_step == ConversationState.MAIN_MENU
    assert state.response_text
    assert services.persisted_steps[-1] == ConversationState.MAIN_MENU


@pytest.mark.asyncio
async def test_asado_menu_transitions_to_select_asado() -> None:
    services = FakeConversationServices()
    state = ConversationGraphState(chat_id=123, raw_text="asado")

    state = await nodes.normalize_message(state, services)
    state = await nodes.detect_intent(state, services)
    assert state.intent == ConversationIntent.MENU_ASADO
    assert route_after_intent(state) == "show_asado_menu"

    state = await nodes.show_asado_menu(state, services)

    assert state.current_step == ConversationState.SELECT_ASADO
    assert "1. 1/2 Asado" in state.response_text


@pytest.mark.asyncio
async def test_main_menu_number_one_shows_categories() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.MAIN_MENU)
    state = ConversationGraphState(chat_id=123, raw_text="1")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert state.intent == ConversationIntent.VER_MENU
    assert route_after_intent(state) == "show_product_categories"


@pytest.mark.asyncio
async def test_main_menu_number_two_enters_natural_order() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.MAIN_MENU)
    state = ConversationGraphState(chat_id=123, raw_text="2")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert state.intent == ConversationIntent.LENGUAJE_NATURAL
    assert route_after_intent(state) == "fallback_natural_language"


@pytest.mark.asyncio
async def test_hola_from_natural_order_returns_to_main_menu() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.NATURAL_ORDER)
    state = ConversationGraphState(chat_id=123, raw_text="Hola")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    state = await nodes.show_main_menu(state, services)

    assert state.intent == ConversationIntent.MOSTRAR_MENU
    assert state.current_step == ConversationState.MAIN_MENU
    assert "bienvenido" in state.response_text.lower()
    assert "Pedir por menu" in state.response_text
    assert "Pedir escribiendo" in state.response_text


@pytest.mark.asyncio
async def test_real_customer_polite_order_does_not_show_welcome_menu() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Buenas tardes me regalas porfa un pollo asado con yuca frita",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "Bienvenido" not in result["response_text"]
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert "1 x Yuca frita" in result["response_text"]
    assert len(services.session.cart) == 2


@pytest.mark.asyncio
async def test_real_customer_two_roasted_chickens_order_is_added() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Me hace el favor y me vende 2 pollos asados",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "2 x 1 Asado Entero" in result["response_text"]
    assert services.session.cart[0].quantity == 2


@pytest.mark.asyncio
async def test_real_customer_lasagna_availability_question_is_not_a_greeting() -> None:
    services = FakeConversationServices()
    state = ConversationGraphState(
        chat_id=123,
        raw_text="buenas tardes, les queda lasagna? gracias",
    )

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert state.intent == ConversationIntent.RESPONDER_CONSULTA
    assert state.query_type == "availability"
    assert state.query_value == "lasagna mixta"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_text",
    [
        "hay lasaña hoy?",
        "buenas, tienen lasagna mixta?",
        "les quedo lasaña?",
        "todavia manejan lasana?",
        "buenas tardes, venden maduros con queso?",
    ],
)
async def test_real_customer_availability_questions_go_to_catalog(raw_text: str) -> None:
    services = FakeConversationServices()
    state = ConversationGraphState(chat_id=123, raw_text=raw_text)

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert state.intent == ConversationIntent.RESPONDER_CONSULTA
    if "maduro" in state.normalized_text:
        assert state.query_type == "category"
        assert state.query_value == "especiales"
    else:
        assert state.query_type == "availability"
        assert state.query_value == "lasagna mixta"


@pytest.mark.asyncio
async def test_customer_gave_up_by_phone_cancels_instead_of_reprompting() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Ya no ya lo pedí por teléfono Gracias")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.MAIN_MENU
    assert "cancele el pedido actual" in result["response_text"]
    assert "Puedes escribirme tu pedido" not in result["response_text"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_text",
    [
        "no gracias ya llamé",
        "tranqui ya lo pedi por telefono",
        "ya no, muchas gracias",
        "cancele porfa ya lo solucioné",
    ],
)
async def test_real_customer_gave_up_variants_cancel_without_reprompting(raw_text: str) -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text=raw_text)

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.MAIN_MENU
    assert "cancele el pedido actual" in result["response_text"]
    assert "Puedes escribirme tu pedido" not in result["response_text"]


@pytest.mark.asyncio
async def test_main_menu_clears_pending_product_selection() -> None:
    services = FakeConversationServices()
    services.session.selected_product_code = ProductCode("ASADO_34")
    services.session.selected_chicken_part = "2 pechugas y 1 pierna"
    services.session.move_to(ConversationState.ASK_CHICKEN_PART)
    state = ConversationGraphState(chat_id=123, raw_text="hola")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    state = await nodes.show_main_menu(state, services)

    assert state.current_step == ConversationState.MAIN_MENU
    assert services.session.selected_product_code is None
    assert services.session.selected_chicken_part is None


@pytest.mark.asyncio
async def test_main_menu_number_three_shows_cart() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.MAIN_MENU)
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    services.session.move_to(ConversationState.MAIN_MENU)
    state = ConversationGraphState(chat_id=123, raw_text="3")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert state.intent == ConversationIntent.MOSTRAR_CARRITO
    assert route_after_intent(state) == "show_cart"


@pytest.mark.asyncio
async def test_natural_cart_query_shows_cart() -> None:
    services = FakeConversationServices()
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    state = ConversationGraphState(chat_id=123, raw_text="quiero ver mi carrito")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert state.intent == ConversationIntent.MOSTRAR_CARRITO
    assert route_after_intent(state) == "show_cart"


@pytest.mark.asyncio
async def test_natural_clear_cart_command_clears_cart() -> None:
    services = FakeConversationServices()
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    state = ConversationGraphState(chat_id=123, raw_text="quiero vaciar el carrito")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert state.intent == ConversationIntent.VACIAR_CARRITO
    assert route_after_intent(state) == "clear_cart"

    state = await nodes.clear_cart(state, services)

    assert services.session.cart == []
    assert "vacie tu carrito" in state.response_text


@pytest.mark.asyncio
async def test_lasagna_request_uses_fast_rules_before_business_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nodes, "_business_today", lambda: date(2026, 7, 14))
    services = FakeConversationServices()
    state = ConversationGraphState(chat_id=123, raw_text="quiero pedir una lasaña")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    state = await nodes.fallback_natural_language(state, services)

    assert state.intent == ConversationIntent.PRODUCTO_RESTRINGIDO
    assert "Lasagna Mixta no esta disponible en este momento" in state.response_text
    assert "Te puedo ofrecer Maduro con Queso" in state.response_text
    assert "no cuento con informacion" not in state.response_text.lower()


@pytest.mark.asyncio
async def test_zero_from_categories_goes_back_to_main_menu() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.PRODUCT_CATEGORY)
    state = ConversationGraphState(chat_id=123, raw_text="0")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    state = await nodes.go_back(state, services)

    assert state.intent == ConversationIntent.VOLVER
    assert state.current_step == ConversationState.MAIN_MENU
    assert "Pedir por menu" in state.response_text


@pytest.mark.asyncio
async def test_zero_from_product_menu_goes_back_to_categories() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.SELECT_ASADO)
    state = ConversationGraphState(chat_id=123, raw_text="0")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    state = await nodes.go_back(state, services)

    assert state.intent == ConversationIntent.VOLVER
    assert state.current_step == ConversationState.PRODUCT_CATEGORY
    assert "Pollo asado" in state.response_text


@pytest.mark.asyncio
async def test_natural_back_from_product_menu_goes_back_to_categories() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.SELECT_BROASTER)
    state = ConversationGraphState(chat_id=123, raw_text="volver a categorías")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    state = await nodes.go_back(state, services)

    assert state.intent == ConversationIntent.VOLVER
    assert state.current_step == ConversationState.PRODUCT_CATEGORY
    assert "Elige una categoria" in state.response_text


@pytest.mark.asyncio
async def test_natural_back_from_variant_menu_goes_back_to_categories() -> None:
    services = FakeConversationServices()
    services.session.selected_product_code = ProductCode("GASEOSA_25")
    services.session.move_to(ConversationState.ASK_PRODUCT_VARIANT)
    state = ConversationGraphState(chat_id=123, raw_text="volver a categorias")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    state = await nodes.go_back(state, services)

    assert state.intent == ConversationIntent.VOLVER
    assert state.current_step == ConversationState.PRODUCT_CATEGORY
    assert "Bebidas" in state.response_text


@pytest.mark.asyncio
async def test_schedules_show_real_hours() -> None:
    services = FakeConversationServices()
    state = ConversationGraphState(chat_id=123, raw_text="4")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    state = await nodes.show_schedules(state, services)

    assert "Lunes a domingo" in state.response_text
    assert "10:00 a.m. a 4:00 p.m." in state.response_text
    assert "0." in state.response_text


@pytest.mark.asyncio
async def test_number_four_after_viewing_cart_clears_cart() -> None:
    services = FakeConversationServices()
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    services.session.move_to(ConversationState.MAIN_MENU)
    state = ConversationGraphState(chat_id=123, raw_text="3")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert state.intent == ConversationIntent.MOSTRAR_CARRITO

    state = await nodes.show_cart(state, services)

    assert services.session.current_step == ConversationState.POST_ADD

    state = ConversationGraphState(chat_id=123, raw_text="4")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert state.intent == ConversationIntent.VACIAR_CARRITO


@pytest.mark.asyncio
async def test_category_number_one_routes_to_asado_menu() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.PRODUCT_CATEGORY)
    state = ConversationGraphState(chat_id=123, raw_text="1")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    state = await nodes.show_asado_menu(state, services)

    assert state.intent == ConversationIntent.MENU_ASADO
    assert state.current_step == ConversationState.SELECT_ASADO
    assert "1. 1/2 Asado" in state.response_text


@pytest.mark.asyncio
async def test_category_number_two_routes_to_broaster_menu() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.PRODUCT_CATEGORY)
    state = ConversationGraphState(chat_id=123, raw_text="2")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    state = await nodes.show_broaster_menu(state, services)

    assert state.intent == ConversationIntent.MENU_BROASTER
    assert state.current_step == ConversationState.SELECT_BROASTER
    assert "1. 1/2 Broasted" in state.response_text


@pytest.mark.asyncio
async def test_category_number_six_asks_for_customer_data() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.PRODUCT_CATEGORY)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="6",
        cart=[
            CartLineState(
                product_code="ASADO_MEDIO",
                product_name="1/2 Asado",
                unit_price_cop=22300,
                quantity=2,
                subtotal_cop=44600,
            )
        ],
    )

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state.cart = [
        CartLineState(
            product_code="ASADO_MEDIO",
            product_name="1/2 Asado",
            unit_price_cop=22300,
            quantity=2,
            subtotal_cop=44600,
        )
    ]
    state = await nodes.detect_intent(state, services)

    assert state.intent == ConversationIntent.PEDIR_DATOS_CLIENTE
    assert route_after_intent(state) == "ask_customer_data"


@pytest.mark.asyncio
async def test_category_product_number_selects_product_and_asks_quantity() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.SELECT_ASADO)
    state = ConversationGraphState(chat_id=123, raw_text="1")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    assert route_after_intent(state) == "select_product"

    state = await nodes.select_product(state, services)
    state = await nodes.validate_product_availability(state, services)
    state = await nodes.ask_quantity(state, services)

    assert state.current_step == ConversationState.ASK_QUANTITY
    assert state.selected_product_code == "ASADO_MEDIO"
    assert "Cuantas unidades" in state.response_text


@pytest.mark.asyncio
async def test_selected_product_transitions_to_ask_quantity() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.SELECT_ASADO)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="ASADO_MEDIO",
        normalized_text="asado_medio",
        current_step=ConversationState.SELECT_ASADO,
    )

    state = await nodes.select_product(state, services)
    state = await nodes.validate_product_availability(state, services)
    state = await nodes.ask_quantity(state, services)

    assert state.current_step == ConversationState.ASK_QUANTITY
    assert state.selected_product_code == "ASADO_MEDIO"
    assert services.session.selected_product_code == ProductCode("ASADO_MEDIO")


@pytest.mark.asyncio
async def test_natural_product_selection_inside_specials_menu_reports_restriction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(nodes, "_business_today", lambda: date(2026, 7, 1))
    services = FakeConversationServices()
    services.session.move_to(ConversationState.SELECT_ESPECIAL)
    state = ConversationGraphState(chat_id=123, raw_text="quiero una lasagna")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert route_after_intent(state) == "select_product"

    state = await nodes.select_product(state, services)
    state = await nodes.validate_product_availability(state, services)

    assert state.intent == ConversationIntent.PRODUCTO_RESTRINGIDO
    assert state.selected_product_code == "MADURO_QUESO"
    assert "Lasagna Mixta no esta disponible en este momento" in state.response_text
    assert "Te puedo ofrecer Maduro con Queso" in state.response_text


@pytest.mark.asyncio
async def test_quarter_asado_asks_for_chicken_part_before_quantity() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.SELECT_ASADO)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="ASADO_CUARTO",
        normalized_text="asado_cuarto",
        current_step=ConversationState.SELECT_ASADO,
    )

    state = await nodes.select_product(state, services)
    state = await nodes.validate_product_availability(state, services)
    state = await nodes.ask_quantity(state, services)

    assert state.current_step == ConversationState.ASK_CHICKEN_PART
    assert state.selected_product_code == "ASADO_CUARTO"
    assert "pierna o pechuga" in state.response_text
    assert services.session.current_step == ConversationState.ASK_CHICKEN_PART
    assert services.session.selected_product_code == ProductCode("ASADO_CUARTO")


@pytest.mark.asyncio
async def test_chicken_part_response_then_asks_quantity() -> None:
    services = FakeConversationServices()
    services.session.selected_product_code = ProductCode("BROASTER_CUARTO")
    services.session.move_to(ConversationState.ASK_CHICKEN_PART)
    state = ConversationGraphState(chat_id=123, raw_text="pechuga")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert state.intent == ConversationIntent.PEDIR_CANTIDAD
    assert route_after_intent(state) == "ask_quantity"

    state = await nodes.ask_quantity(state, services)

    assert state.current_step == ConversationState.ASK_QUANTITY
    assert services.session.selected_chicken_part == "Pechuga"
    assert "1/4 Broasted - Pechuga" in state.response_text


@pytest.mark.asyncio
async def test_product_variant_response_by_name_then_asks_quantity() -> None:
    services = FakeConversationServices()
    services.session.selected_product_code = ProductCode("GASEOSA_25")
    services.session.move_to(ConversationState.ASK_PRODUCT_VARIANT)
    state = ConversationGraphState(chat_id=123, raw_text="pepsi")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert state.intent == ConversationIntent.PEDIR_CANTIDAD
    assert route_after_intent(state) == "ask_quantity"

    state = await nodes.ask_quantity(state, services)

    assert state.current_step == ConversationState.ASK_QUANTITY
    assert services.session.selected_chicken_part == "Pepsi"
    assert "Gaseosa 2.5 L - Pepsi" in state.response_text


@pytest.mark.asyncio
async def test_quarter_product_adds_selected_chicken_part_to_cart_name() -> None:
    services = FakeConversationServices()
    services.session.selected_product_code = ProductCode("ASADO_CUARTO")
    services.session.selected_chicken_part = "Pierna"
    services.session.move_to(ConversationState.ASK_QUANTITY)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="1",
        normalized_text="1",
        current_step=ConversationState.ASK_QUANTITY,
        selected_product_code="ASADO_CUARTO",
        selected_chicken_part="Pierna",
        quantity=1,
    )

    state = await nodes.add_to_cart(state, services)

    assert state.current_step == ConversationState.POST_ADD
    assert state.cart[0].product_name == "1/4 Asado - Pierna"
    assert services.session.cart[0].product_name == ProductName("1/4 Asado - Pierna")
    assert services.session.selected_chicken_part is None


@pytest.mark.asyncio
async def test_natural_quarter_order_without_part_asks_for_chicken_part() -> None:
    services = FakeConversationServices()
    state = ConversationGraphState(chat_id=123, raw_text="quiero un cuarto broaster")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.fallback_natural_language(state, services)

    assert state.current_step == ConversationState.ASK_CHICKEN_PART
    assert state.selected_product_code == "BROASTER_CUARTO"
    assert "pierna o pechuga" in state.response_text
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_natural_quarter_order_with_part_adds_variant_to_cart() -> None:
    services = FakeConversationServices()
    state = ConversationGraphState(chat_id=123, raw_text="quiero un cuarto asado pechuga")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.fallback_natural_language(state, services)

    assert state.current_step == ConversationState.POST_ADD
    assert state.cart[0].product_name == "1/4 Asado - Pechuga"
    assert services.session.cart[0].product_name == ProductName("1/4 Asado - Pechuga")


@pytest.mark.asyncio
async def test_three_quarter_broaster_asks_for_composition_before_quantity() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.SELECT_BROASTER)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="BROASTER_34",
        normalized_text="broaster_34",
        current_step=ConversationState.SELECT_BROASTER,
    )

    state = await nodes.select_product(state, services)
    state = await nodes.validate_product_availability(state, services)
    state = await nodes.ask_quantity(state, services)

    assert state.current_step == ConversationState.ASK_CHICKEN_PART
    assert "2 piernas y 1 pechuga" in state.response_text
    assert "2 pechugas y 1 pierna" in state.response_text


@pytest.mark.asyncio
async def test_three_quarter_composition_response_then_asks_quantity() -> None:
    services = FakeConversationServices()
    services.session.selected_product_code = ProductCode("ASADO_34")
    services.session.move_to(ConversationState.ASK_CHICKEN_PART)
    state = ConversationGraphState(chat_id=123, raw_text="2")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    state = await nodes.ask_quantity(state, services)

    assert state.current_step == ConversationState.ASK_QUANTITY
    assert services.session.selected_chicken_part == "2 pechugas y 1 pierna"
    assert "3/4 Asado - 2 pechugas y 1 pierna" in state.response_text


@pytest.mark.asyncio
async def test_three_quarter_composition_text_does_not_become_quantity() -> None:
    services = FakeConversationServices()
    services.session.selected_product_code = ProductCode("ASADO_34")
    services.session.move_to(ConversationState.ASK_CHICKEN_PART)
    state = ConversationGraphState(chat_id=123, raw_text="2 pechugas y una pierna")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    state = await nodes.ask_quantity(state, services)

    assert state.current_step == ConversationState.ASK_QUANTITY
    assert state.quantity is None
    assert services.session.selected_chicken_part == "2 pechugas y 1 pierna"
    assert "¿Cuantas unidades deseas agregar?" in state.response_text


@pytest.mark.asyncio
async def test_three_quarter_full_flow_with_composition_phrase_waits_for_quantity() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    first = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="quiero pedir tres cuartos de asado"))

    assert first["current_step"] == ConversationState.ASK_CHICKEN_PART
    assert "2 pechugas y 1 pierna" in first["response_text"]
    assert services.session.selected_product_code == ProductCode("ASADO_34")

    second = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Quiero 2 pechugas y una pierna"))

    assert second["current_step"] == ConversationState.ASK_QUANTITY
    assert second.get("quantity") is None
    assert "¿Cuantas unidades deseas agregar?" in second["response_text"]
    assert services.session.cart == []
    assert services.session.selected_chicken_part == "2 pechugas y 1 pierna"


@pytest.mark.asyncio
async def test_natural_three_quarter_order_with_composition_adds_variant_to_cart() -> None:
    services = FakeConversationServices()
    state = ConversationGraphState(
        chat_id=123,
        raw_text="quiero tres cuartos broaster con 2 piernas y una pechuga",
    )

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.fallback_natural_language(state, services)

    assert state.current_step == ConversationState.POST_ADD
    assert state.cart[0].product_name == "3/4 Broasted - 2 piernas y 1 pechuga"


@pytest.mark.asyncio
async def test_quantity_adds_item_and_transitions_to_post_add() -> None:
    services = FakeConversationServices()
    services.session.selected_product_code = ProductCode("ASADO_MEDIO")
    services.session.move_to(ConversationState.ASK_QUANTITY)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="2",
        normalized_text="2",
        current_step=ConversationState.ASK_QUANTITY,
        selected_product_code="ASADO_MEDIO",
        quantity=2,
    )

    state = await nodes.add_to_cart(state, services)

    assert state.current_step == ConversationState.POST_ADD
    assert state.cart[0].subtotal_cop == 44600
    assert services.session.cart_total == MoneyCOP(44600)
    assert services.session.current_step == ConversationState.POST_ADD
    assert "1. Agregar mas productos" in state.response_text
    assert "3. Finalizar pedido" in state.response_text


@pytest.mark.asyncio
async def test_quantity_phrase_adds_waiting_product_to_cart() -> None:
    services = FakeConversationServices()
    services.session.selected_product_code = ProductCode("ASADO_CUARTO")
    services.session.selected_chicken_part = "Pierna"
    services.session.move_to(ConversationState.ASK_QUANTITY)
    state = ConversationGraphState(chat_id=123, raw_text="quiero 2")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert state.intent == ConversationIntent.AGREGAR_PRODUCTO
    assert state.quantity == 2
    assert route_after_intent(state) == "add_to_cart"

    state = await nodes.add_to_cart(state, services)

    assert state.current_step == ConversationState.POST_ADD
    assert state.cart[0].product_name == "1/4 Asado - Pierna"
    assert state.cart[0].quantity == 2


@pytest.mark.asyncio
async def test_hola_while_waiting_quantity_returns_main_menu() -> None:
    services = FakeConversationServices()
    services.session.selected_product_code = ProductCode("BROASTER_CUARTO")
    services.session.selected_chicken_part = "Pierna"
    services.session.move_to(ConversationState.ASK_QUANTITY)
    state = ConversationGraphState(chat_id=123, raw_text="hola")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert state.intent == ConversationIntent.MOSTRAR_MENU
    assert route_after_intent(state) == "show_main_menu"


@pytest.mark.asyncio
async def test_post_add_number_three_asks_for_customer_data() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.POST_ADD)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="3",
    )

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state.cart = [
        CartLineState(
            product_code="ASADO_MEDIO",
            product_name="1/2 Asado",
            unit_price_cop=22300,
            quantity=2,
            subtotal_cop=44600,
        )
    ]
    state = await nodes.detect_intent(state, services)

    assert state.intent == ConversationIntent.PEDIR_DATOS_CLIENTE
    assert route_after_intent(state) == "ask_customer_data"


@pytest.mark.asyncio
async def test_post_add_hola_keeps_cart_context() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.POST_ADD)
    state = ConversationGraphState(chat_id=123, raw_text="hola")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert state.intent == ConversationIntent.MOSTRAR_CARRITO
    assert route_after_intent(state) == "show_cart"


@pytest.mark.asyncio
async def test_post_add_text_finalizar_asks_for_customer_data() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.POST_ADD)
    state = ConversationGraphState(chat_id=123, raw_text="finalizar")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert state.intent == ConversationIntent.PEDIR_DATOS_CLIENTE
    assert route_after_intent(state) == "ask_customer_data"


@pytest.mark.asyncio
async def test_finalizar_asks_for_customer_data_before_confirmation() -> None:
    services = FakeConversationServices()
    state = ConversationGraphState(
        chat_id=123,
        raw_text="finalizar",
        cart=[
            CartLineState(
                product_code="ASADO_MEDIO",
                product_name="1/2 Asado",
                unit_price_cop=22300,
                quantity=2,
                subtotal_cop=44600,
            )
        ],
    )

    state = await nodes.normalize_message(state, services)
    state = await nodes.detect_intent(state, services)
    assert state.intent == ConversationIntent.PEDIR_DATOS_CLIENTE

    state = await nodes.ask_customer_data(state, services)

    assert state.current_step == ConversationState.ASK_CUSTOMER_DATA
    assert "Nombre completo" in state.response_text
    assert "Telefono" in state.response_text
    assert "Direccion" in state.response_text
    assert "Barrio" in state.response_text
    assert "Nota o especificacion" in state.response_text


@pytest.mark.asyncio
async def test_customer_data_creates_review_before_confirmation() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    state = ConversationGraphState(
        chat_id=123,
        raw_text=(
            "Nombre completo: Juan Perez\n"
            "Telefono: 3001234567\n"
            "Direccion: Calle 1 # 2-3\n"
            "Barrio: Provenza\n"
            "Nota o especificacion: sin cebolla\n"
            "Metodo de pago: Nequi"
        ),
        cart=[
            CartLineState(
                product_code="ASADO_MEDIO",
                product_name="1/2 Asado",
                unit_price_cop=22300,
                quantity=2,
                subtotal_cop=44600,
            )
        ],
    )

    state = await nodes.extract_customer_data(state, services)
    state = await nodes.validate_customer_data(state, services)

    assert not state.errors
    assert state.current_step == ConversationState.CHECKOUT_REVIEW
    assert route_after_customer_validation(state) == "calculate_delivery"

    state = await nodes.calculate_delivery(state, services)
    state = await nodes.create_order(state, services)

    assert state.current_step == ConversationState.CHECKOUT_REVIEW
    assert "Datos recibidos" in state.response_text
    assert "Juan Perez" in state.response_text
    assert "Responde SI" in state.response_text


@pytest.mark.asyncio
async def test_customer_data_accepts_free_line_message() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Wendy\n3022873946\nCra 28a#195-33\nLagos 2\nEfectivo\nNinguna",
        cart=[
            CartLineState(
                product_code="ASADO_MEDIO",
                product_name="1/2 Asado",
                unit_price_cop=22300,
                quantity=2,
                subtotal_cop=44600,
            )
        ],
    )

    state = await nodes.extract_customer_data(state, services)
    state = await nodes.validate_customer_data(state, services)

    assert not state.errors
    assert state.customer.name == "Wendy"
    assert state.customer.phone == "3022873946"
    assert state.customer.address == "Cra 28a#195-33"
    assert state.customer.neighborhood == "Lagos 2"
    assert state.customer.observations == "Ninguna"
    assert state.customer.payment_method == "Efectivo"
    assert state.current_step == ConversationState.CHECKOUT_REVIEW


@pytest.mark.asyncio
async def test_pickup_customer_data_only_requires_name_and_phone() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    services.session.fulfillment_type = "PICKUP"
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Angel David\n3153327502\nsin cebolla",
        fulfillment_type="PICKUP",
        cart=[
            CartLineState(
                product_code="ASADO_MEDIO",
                product_name="1/2 Asado",
                unit_price_cop=22300,
                quantity=1,
                subtotal_cop=22300,
            )
        ],
    )

    state = await nodes.extract_customer_data(state, services)
    state = await nodes.validate_customer_data(state, services)
    state = await nodes.calculate_delivery(state, services)
    state = await nodes.create_order(state, services)

    assert not state.errors
    assert state.current_step == ConversationState.CHECKOUT_REVIEW
    assert state.customer.name == "Angel David"
    assert state.customer.phone == "3153327502"
    assert state.customer.address == "Recoge en local"
    assert state.customer.neighborhood == "No aplica"
    assert state.customer.payment_method == "No aplica"
    assert state.delivery_price_cop == 0
    assert "Recoge en local" in state.response_text
    assert "Domicilio: $0" in state.response_text


@pytest.mark.asyncio
async def test_customer_data_accepts_checkout_without_optional_note() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Wendy\n3022873946\nCra 28a#195-33\nEl Manantial\nEfectivo",
        cart=[
            CartLineState(
                product_code="ASADO_MEDIO",
                product_name="1/2 Asado",
                unit_price_cop=22300,
                quantity=2,
                subtotal_cop=44600,
            )
        ],
    )

    state = await nodes.extract_customer_data(state, services)
    state = await nodes.validate_customer_data(state, services)

    assert not state.errors
    assert state.customer.name == "Wendy"
    assert state.customer.phone == "3022873946"
    assert state.customer.address == "Cra 28a#195-33"
    assert state.customer.neighborhood == "El Manantial"
    assert state.customer.payment_method == "Efectivo"
    assert state.customer.observations is None
    assert state.current_step == ConversationState.CHECKOUT_REVIEW


@pytest.mark.asyncio
async def test_customer_data_ignores_greetings_cached_before_real_checkout_data() -> None:
    services = FakeConversationServices()
    services.session.customer_name = "Buenos dias"
    services.session.customer_neighborhood = "Buenos dias"
    services.session.observations = "Buenos dias"
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Wendy\n3022873946\nCra28a#195-33\nEl manantial\nEfectivo",
    )

    state = await nodes.load_or_create_session(state, services)
    state = await nodes.extract_customer_data(state, services)
    state = await nodes.validate_customer_data(state, services)

    assert not state.errors
    assert state.customer.name == "Wendy"
    assert state.customer.phone == "3022873946"
    assert state.customer.address == "Cra28a#195-33"
    assert state.customer.neighborhood == "El manantial"
    assert state.customer.observations is None
    assert state.customer.payment_method == "Efectivo"


@pytest.mark.asyncio
async def test_customer_data_ignores_polite_lines_inside_checkout_form() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    state = ConversationGraphState(
        chat_id=123,
        raw_text=(
            "Buenas tardes\n"
            "Wendy\n"
            "3022873946\n"
            "Cra28a#195-33\n"
            "El manantial\n"
            "Muchas gracias\n"
            "Nequi"
        ),
    )

    state = await nodes.load_or_create_session(state, services)
    state = await nodes.extract_customer_data(state, services)
    state = await nodes.validate_customer_data(state, services)

    assert not state.errors
    assert state.customer.name == "Wendy"
    assert state.customer.phone == "3022873946"
    assert state.customer.address == "Cra28a#195-33"
    assert state.customer.neighborhood == "El manantial"
    assert state.customer.payment_method == "Nequi"
    assert state.customer.observations is None


@pytest.mark.asyncio
async def test_customer_data_keeps_address_and_neighborhood_when_sent_after_order_text() -> None:
    services = FakeConversationServices()
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Carlos\n3152223344\ncalle 196 # 29 -71\nvillas de san fransisco\nefectivo",
    )

    state = await nodes.load_or_create_session(state, services)
    state = await nodes.extract_customer_data(state, services)
    state = await nodes.validate_customer_data(state, services)

    assert not state.errors
    assert state.customer.name == "Carlos"
    assert state.customer.phone == "3152223344"
    assert state.customer.address == "calle 196 # 29 -71"
    assert state.customer.neighborhood == "villas de san fransisco"
    assert state.customer.payment_method == "Efectivo"


@pytest.mark.asyncio
async def test_customer_data_requires_payment_method_when_note_is_present() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Wendy\n3022873946\nCra 28a#195-33\nEl Manantial\nSin salsas",
        cart=[
            CartLineState(
                product_code="ASADO_MEDIO",
                product_name="1/2 Asado",
                unit_price_cop=22300,
                quantity=2,
                subtotal_cop=44600,
            )
        ],
    )

    state = await nodes.extract_customer_data(state, services)
    state = await nodes.validate_customer_data(state, services)

    assert state.errors == ["metodo de pago"]
    assert state.current_step == ConversationState.ASK_CUSTOMER_DATA
    assert state.customer.observations == "Sin salsas"


@pytest.mark.asyncio
async def test_customer_data_keeps_partial_fields_when_one_field_is_missing() -> None:
    services = FakeConversationServices()
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    first_state = ConversationGraphState(
        chat_id=123,
        raw_text="Angel David Pinzon\n3153327502\nTransversal 23 #52A-21\nEfectivo",
    )

    first_state = await nodes.load_or_create_session(first_state, services)
    first_state = await nodes.extract_customer_data(first_state, services)
    first_state = await nodes.validate_customer_data(first_state, services)

    assert first_state.errors == ["barrio"]
    assert services.session.customer_name == "Angel David Pinzon"
    assert services.session.customer_phone == "3153327502"
    assert services.session.customer_address == "Transversal 23 #52A-21"
    assert services.session.payment_method == "Efectivo"

    second_state = ConversationGraphState(
        chat_id=123,
        raw_text="San Antonio del Carrizal, Giron",
    )

    second_state = await nodes.load_or_create_session(second_state, services)
    second_state = await nodes.extract_customer_data(second_state, services)
    second_state = await nodes.validate_customer_data(second_state, services)

    assert not second_state.errors
    assert second_state.current_step == ConversationState.CHECKOUT_REVIEW
    assert second_state.customer.name == "Angel David Pinzon"
    assert second_state.customer.phone == "3153327502"
    assert second_state.customer.address == "Transversal 23 #52A-21"
    assert second_state.customer.neighborhood == "San Antonio del Carrizal, Giron"
    assert second_state.customer.payment_method == "Efectivo"


@pytest.mark.asyncio
async def test_customer_data_keeps_partial_fields_when_note_is_sent_without_neighborhood() -> None:
    services = FakeConversationServices()
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    graph = build_conversation_graph(services)

    first_result = await graph.ainvoke(
        ConversationGraphState(
            chat_id=123,
            raw_text="wendy\n3022873946\ncra28a#195-33\nninguna\nefectivo",
        )
    )

    assert "barrio" in first_result["response_text"].lower()
    assert services.session.customer_name == "wendy"
    assert services.session.customer_phone == "3022873946"
    assert services.session.customer_address == "cra28a#195-33"
    assert services.session.customer_neighborhood is None
    assert services.session.observations == "ninguna"
    assert services.session.payment_method == "Efectivo"

    second_result = await graph.ainvoke(
        ConversationGraphState(
            chat_id=123,
            raw_text="el manantial",
        )
    )

    assert "Datos recibidos" in second_result["response_text"]
    assert "Cliente: wendy" in second_result["response_text"]
    assert "Telefono: 3022873946" in second_result["response_text"]
    assert "Direccion: cra28a#195-33" in second_result["response_text"]
    assert "Barrio: el manantial" in second_result["response_text"]
    assert "Pago: Efectivo" in second_result["response_text"]


@pytest.mark.asyncio
async def test_customer_data_does_not_confuse_address_with_phone() -> None:
    services = FakeConversationServices()
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Wendy\n3022873946\nCra 28a#195-33\nLa cumbre\nNinguna",
    )

    state = await nodes.extract_customer_data(state, services)

    assert state.customer.phone == "3022873946"
    assert state.customer.address == "Cra 28a#195-33"
    assert state.customer.neighborhood == "La cumbre"


@pytest.mark.asyncio
async def test_graph_preserves_free_line_customer_data() -> None:
    services = FakeConversationServices()
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 2))
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text=(
            "wendy\n"
            "3022873946\n"
            "cra 28 a #195-33\n"
            "el manantial\n"
            "ninguna\n"
            "efectivo"
        ),
    )

    result = await graph.ainvoke(state)

    assert result.get("errors") in (None, [])
    assert "Datos recibidos" in result["response_text"]
    assert "Cliente: wendy" in result["response_text"]
    assert "Telefono: 3022873946" in result["response_text"]
    assert "Direccion: cra 28 a #195-33" in result["response_text"]
    assert "Barrio: el manantial" in result["response_text"]
    assert "Pago: Efectivo" in result["response_text"]


@pytest.mark.asyncio
async def test_graph_extracts_single_line_customer_data_with_address_and_payment() -> None:
    services = FakeConversationServices()
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Gladys 3168552291 carrea28a No 105 33 el Manatial efectivo",
    )

    result = await graph.ainvoke(state)

    assert result.get("errors") in (None, [])
    assert "Datos recibidos" in result["response_text"]
    assert "Cliente: Gladys" in result["response_text"]
    assert "Telefono: 3168552291" in result["response_text"]
    assert "Direccion: carrea28a No 105 33" in result["response_text"]
    assert "Barrio: el Manatial" in result["response_text"]
    assert "Pago: Efectivo" in result["response_text"]


@pytest.mark.asyncio
async def test_graph_adds_natural_order_items_to_cart() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    services.products["COCA_COLA_15"] = Product(
        code=ProductCode("COCA_COLA_15"),
        name=ProductName("Coca-Cola 1.5 L"),
        category=ProductCategory.BEBIDAS,
        price=MoneyCOP(8500),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Necesito un pollo asado con una Cocacola 1.5",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert "1 x Coca-Cola 1.5 L" in result["response_text"]
    assert "Total acumulado: $53000" in result["response_text"]
    assert len(services.session.cart) == 2


@pytest.mark.asyncio
async def test_natural_order_with_ambiguous_gaseosas_asks_drink_type() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Un pollos asado con 2 gaseosas")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert "tambien quieres 2 gaseosas" in result["response_text"]
    assert "dime cual deseas" in result["response_text"]
    assert "Coca-Cola 1.5 L" in result["response_text"]
    assert len(services.session.cart) == 1


@pytest.mark.asyncio
async def test_natural_order_with_gaseosa_kola_adds_25_liter_kola_directly() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Hola un pollo asado con gaseosa kola")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert "1 x Gaseosa 2.5 L - Kola" in result["response_text"]
    assert "dime cual deseas" not in result["response_text"]
    assert len(services.session.cart) == 2


@pytest.mark.asyncio
async def test_natural_order_with_unavailable_lasagna_explains_not_added() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Muy buenos días me regalas porfa un pollo asado con una lasaña y una gaseosa kola",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.ASK_STOCK_ALTERNATIVE
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert "1 x Gaseosa 2.5 L - Kola" in result["response_text"]
    assert "Lasagna Mixta no esta disponible en este momento" in result["response_text"]
    assert "Te puedo ofrecer Maduro con Queso" in result["response_text"]
    assert "¿Quieres seguir con esta opcion o prefieres ver el menu?" in result["response_text"]
    assert all(item.product_code.value != "LASAGNA_MIXTA" for item in services.session.cart)
    assert len(services.session.cart) == 2


@pytest.mark.asyncio
async def test_lasagna_availability_question_shows_unavailable_alternative() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Hay lasañas?")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.ASK_STOCK_ALTERNATIVE
    assert "Lasagna Mixta no esta disponible en este momento" in result["response_text"]
    assert "Te puedo ofrecer Maduro con Queso" in result["response_text"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_text",
    [
        "En cuanto tiempo me despachan?",
        "En cuanto tiempo se demora",
        "cuanto se demora mi pedido",
        "Tiempo de espera",
    ],
)
async def test_order_timing_questions_answer_without_fallback(raw_text: str) -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text=raw_text)

    result = await graph.ainvoke(state)

    assert "40 minutos o menos" in result["response_text"]
    assert "Puedes escribirme tu pedido" not in result["response_text"]


@pytest.mark.asyncio
async def test_graph_extracts_customer_data_split_by_commas() -> None:
    services = FakeConversationServices()
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Yibeth, Barrio manantial, Efectivo\n3054303858, CRA 28a #195-33",
    )

    result = await graph.ainvoke(state)

    assert result.get("errors") in (None, [])
    assert "Cliente: Yibeth" in result["response_text"]
    assert "Telefono: 3054303858" in result["response_text"]
    assert "Direccion: CRA 28a #195-33" in result["response_text"]
    assert "Barrio: Barrio manantial" in result["response_text"]
    assert "Pago: Efectivo" in result["response_text"]


@pytest.mark.asyncio
async def test_graph_asks_for_chicken_type_when_plain_chicken_is_ambiguous() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="quiero un pollo")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.PRODUCT_CATEGORY
    assert "dime cual quieres" in result["response_text"]
    assert "1. 🍗 Pollo asado" in result["response_text"]
    assert "2. 🍗 Pollo broaster" in result["response_text"]
    assert len(services.session.cart) == 0


@pytest.mark.asyncio
async def test_question_about_gaseosas_lists_products_without_adding_to_cart() -> None:
    services = FakeConversationServices()
    services.products["COCA_COLA_15"] = Product(
        code=ProductCode("COCA_COLA_15"),
        name=ProductName("Coca-Cola 1.5 L"),
        category=ProductCategory.BEBIDAS,
        price=MoneyCOP(8500),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Que gaseosas tienes?")

    result = await graph.ainvoke(state)

    assert "🥤 Bebidas" in result["response_text"]
    assert "Jugos Hit personal: $3000" in result["response_text"]
    assert "Coca-Cola personal 400 ml: $3500" in result["response_text"]
    assert "Coca-Cola 1.5 L: $8500" in result["response_text"]
    assert len(services.session.cart) == 0


@pytest.mark.asyncio
async def test_question_about_product_price_answers_without_cart() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Cuanto vale medio pollo?")

    result = await graph.ainvoke(state)

    assert "1/2 Asado vale $22300" in result["response_text"]
    assert len(services.session.cart) == 0


@pytest.mark.asyncio
async def test_ambiguous_gaseosa_price_question_lists_bebidas() -> None:
    services = FakeConversationServices()
    services.products["COCA_COLA_15"] = Product(
        code=ProductCode("COCA_COLA_15"),
        name=ProductName("Coca-Cola 1.5 L"),
        category=ProductCategory.BEBIDAS,
        price=MoneyCOP(8500),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Cuanto vale una gaseosa?")

    result = await graph.ainvoke(state)

    assert "🥤 Bebidas" in result["response_text"]
    assert "Jugos Hit personal: $3000" in result["response_text"]
    assert "Coca-Cola personal 400 ml: $3500" in result["response_text"]
    assert "Coca-Cola 1.5 L: $8500" in result["response_text"]
    assert "Gaseosa vale $3000" not in result["response_text"]
    assert len(services.session.cart) == 0


@pytest.mark.asyncio
async def test_quantity_step_soup_question_does_not_add_soup_to_cart() -> None:
    services = FakeConversationServices()
    services.session.selected_product_code = ProductCode("BROASTER_MEDIO")
    services.session.move_to(ConversationState.ASK_QUANTITY)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Trae sopa?")

    result = await graph.ainvoke(state)

    assert "incluye 1 sopa sin costo" in result["response_text"].lower()
    assert result["current_step"] == ConversationState.ASK_QUANTITY
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_unavailable_soup_question_prompts_continue_or_cancel() -> None:
    services = FakeConversationServices()
    services.soup_available = False
    services.session.selected_product_code = ProductCode("BROASTER_MEDIO")
    services.session.move_to(ConversationState.ASK_QUANTITY)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Trae sopa?")

    result = await graph.ainvoke(state)

    assert "no contamos con sopas" in result["response_text"].lower()
    assert "¿Quieres seguir con tu pedido o prefieres cancelarlo?" in result["response_text"]
    assert result["current_step"] == ConversationState.ASK_SOUP_UNAVAILABLE
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_continue_without_soup_shows_menu_and_keeps_cart() -> None:
    services = FakeConversationServices()
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    services.session.move_to(ConversationState.ASK_SOUP_UNAVAILABLE)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="seguir")

    result = await graph.ainvoke(state)

    assert "seguimos con tu pedido sin sopa" in result["response_text"].lower()
    assert "Elige una categoria" in result["response_text"]
    assert result["current_step"] == ConversationState.PRODUCT_CATEGORY
    assert len(services.session.cart) == 1


@pytest.mark.asyncio
async def test_cancel_after_unavailable_soup_clears_cart() -> None:
    services = FakeConversationServices()
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    services.session.move_to(ConversationState.ASK_SOUP_UNAVAILABLE)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="cancelar")

    result = await graph.ainvoke(state)

    assert "muchas gracias por elegirnos" in result["response_text"].lower()
    assert result["current_step"] == ConversationState.MAIN_MENU
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_product_contents_question_does_not_add_product_to_cart() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Que trae el pollo a la broster entero")

    result = await graph.ainvoke(state)

    assert "Broasted Entero trae pollo broaster" in result["response_text"]
    assert "Agregado al carrito" not in result["response_text"]
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_combination_question_does_not_add_half_broaster_to_cart() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Puedo pedir medio asado y medio a la broster?")

    result = await graph.ainvoke(state)

    assert "puedes pedir medio asado y medio broaster" in result["response_text"].lower()
    assert "Agregado al carrito" not in result["response_text"]
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_half_combo_order_button_adds_both_halves_to_cart() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.ASK_HALF_COMBO)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="pedir")

    result = await graph.ainvoke(state)

    assert "1 x 1/2 Asado" in result["response_text"]
    assert "1 x 1/2 Broasted" in result["response_text"]
    assert result["current_step"] == ConversationState.POST_ADD
    assert [item.product_code.value for item in services.session.cart] == [
        "ASADO_MEDIO",
        "BROASTER_MEDIO",
    ]


@pytest.mark.asyncio
async def test_half_combo_menu_button_shows_menu_without_adding_cart() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.ASK_HALF_COMBO)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="ver menu")

    result = await graph.ainvoke(state)

    assert "Elige una categoria" in result["response_text"]
    assert result["current_step"] == ConversationState.PRODUCT_CATEGORY
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_lazania_price_typo_answers_product_price() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Que precio tiene la lazaña")

    result = await graph.ainvoke(state)

    assert "Lasagna Mixta vale $20000" in result["response_text"]
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_contents_question_without_product_asks_for_product_context() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Que trae?")

    result = await graph.ainvoke(state)

    assert "Dime de que producto" in result["response_text"]
    assert "Puedes escribirme tu pedido" not in result["response_text"]
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_question_about_delivery_answers_without_ai() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Domicilio para Provenza cuanto es?")

    result = await graph.ainvoke(state)

    assert "domicilio para provenza cuesta $2000" in result["response_text"].lower()
    assert len(services.session.cart) == 0


@pytest.mark.asyncio
async def test_question_about_order_delay_gets_friendly_answer() -> None:
    services = FakeConversationServices()
    state = ConversationGraphState(chat_id=123, raw_text="Por que no llega mi pedido de pollo?")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    state = await nodes.answer_query(state, services)

    assert state.intent == ConversationIntent.RESPONDER_CONSULTA
    assert "40 minutos" in state.response_text
    assert "Gracias por tu paciencia" in state.response_text
    assert len(services.session.cart) == 0


@pytest.mark.asyncio
async def test_new_order_request_is_not_treated_as_order_delay_query() -> None:
    services = FakeConversationServices()
    state = ConversationGraphState(chat_id=123, raw_text="quiero hacer otro pedido de pollo broaster")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    state = await nodes.fallback_natural_language(state, services)

    assert "40 minutos" not in state.response_text
    assert "Claro, te ayudo con otro pedido" in state.response_text
    assert "Pollo broaster" in state.response_text
    assert state.current_step == ConversationState.SELECT_BROASTER
    assert len(services.session.cart) == 0


@pytest.mark.asyncio
async def test_out_of_scope_question_is_rejected_without_cart() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Hazme un hola mundo en python")

    result = await graph.ainvoke(state)

    assert "No cuento con informacion" in result["response_text"]
    assert len(services.session.cart) == 0


@pytest.mark.asyncio
async def test_unknown_asadero_product_gets_polite_catalog_answer() -> None:
    services = FakeConversationServices()
    state = ConversationGraphState(chat_id=123, raw_text="Necesito un pescado frito")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    result = await nodes.fallback_natural_language(state, services)

    assert "no cuento con informacion de ese producto" in result.response_text.lower()
    assert result.current_step == ConversationState.PRODUCT_CATEGORY
    assert len(services.session.cart) == 0


@pytest.mark.asyncio
async def test_weekend_special_natural_order_adds_lasagna_to_cart(monkeypatch) -> None:
    monkeypatch.setattr(nodes, "_business_today", lambda: date(2026, 7, 4))
    services = FakeConversationServices()
    services.products["LASAGNA_MIXTA"] = Product(
        code=ProductCode("LASAGNA_MIXTA"),
        name=ProductName("Lasagna Mixta"),
        category=ProductCategory.ESPECIALES,
        price=MoneyCOP(20000),
        restricted_to=ProductRestriction.WEEKEND_OR_HOLIDAY,
    )
    state = ConversationGraphState(chat_id=123, raw_text="quiero una lasaaña")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    result = await nodes.fallback_natural_language(state, services)

    assert result.current_step == ConversationState.POST_ADD
    assert "1 x Lasagna Mixta" in result.response_text
    assert len(services.session.cart) == 1


@pytest.mark.asyncio
async def test_weekday_special_natural_order_stays_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(nodes, "_business_today", lambda: date(2026, 7, 1))
    services = FakeConversationServices()
    services.products["LASAGNA_MIXTA"] = Product(
        code=ProductCode("LASAGNA_MIXTA"),
        name=ProductName("Lasagna Mixta"),
        category=ProductCategory.ESPECIALES,
        price=MoneyCOP(20000),
        restricted_to=ProductRestriction.WEEKEND_OR_HOLIDAY,
    )
    state = ConversationGraphState(chat_id=123, raw_text="quiero una lasaña")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    result = await nodes.fallback_natural_language(state, services)

    assert "no esta disponible en este momento" in result.response_text.lower()
    assert "Maduro con Queso" in result.response_text
    assert len(services.session.cart) == 0


@pytest.mark.asyncio
async def test_menu_request_recovers_after_unknown_natural_order() -> None:
    services = FakeConversationServices()

    first_state = ConversationGraphState(chat_id=123, raw_text="quiero un producto que no existe")
    first_state = await nodes.normalize_message(first_state, services)
    first_state = await nodes.load_or_create_session(first_state, services)
    first_state = await nodes.detect_intent(first_state, services)
    first_result = await nodes.fallback_natural_language(first_state, services)

    second_state = ConversationGraphState(chat_id=123, raw_text="quiero ver el menu")
    second_state = await nodes.normalize_message(second_state, services)
    second_state = await nodes.load_or_create_session(second_state, services)
    second_state = await nodes.detect_intent(second_state, services)
    assert route_after_intent(second_state) == "show_product_categories"
    second_result = await nodes.show_product_categories(second_state, services)

    assert first_result.current_step == ConversationState.PRODUCT_CATEGORY
    assert "Elige una categoria" in second_result.response_text
    assert second_result.current_step == ConversationState.PRODUCT_CATEGORY


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected_route"),
    [
        ("quiero ver el menu principal", "show_main_menu"),
        ("hola buenas", "show_main_menu"),
        ("quiero pedir por menu", "show_product_categories"),
        ("quiero pedir escribiendo", "fallback_natural_language"),
        ("quiero ver carrito", "show_cart"),
        ("quiero ver horarios", "show_schedules"),
        ("quiero finalizar pedido", "ask_customer_data"),
        ("quiero finalizar mi pedidso", "ask_customer_data"),
        ("quiero fnalizar mi pedidso", "ask_customer_data"),
        ("quiero ver mi carito", "show_cart"),
        ("quiero ver platos especiales", "show_specials_menu"),
    ],
)
async def test_main_menu_options_work_as_natural_language(
    message: str,
    expected_route: str,
) -> None:
    services = FakeConversationServices()
    state = ConversationGraphState(chat_id=123, raw_text=message)

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert route_after_intent(state) == expected_route


@pytest.mark.asyncio
async def test_short_litro_medio_question_answers_price() -> None:
    services = FakeConversationServices()
    services.products["COCA_COLA_15"] = Product(
        code=ProductCode("COCA_COLA_15"),
        name=ProductName("Coca-Cola 1.5 L"),
        category=ProductCategory.BEBIDAS,
        price=MoneyCOP(8500),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="La 1.5?")

    result = await graph.ainvoke(state)

    assert "Coca-Cola 1.5 L vale $8500" in result["response_text"]
    assert len(services.session.cart) == 0


@pytest.mark.asyncio
async def test_graph_adds_natural_order_additional_items_to_cart() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    services.products["COCA_COLA_15"] = Product(
        code=ProductCode("COCA_COLA_15"),
        name=ProductName("Coca-Cola 1.5 L"),
        category=ProductCategory.BEBIDAS,
        price=MoneyCOP(8500),
    )
    services.products["PAPA_FRANCESA"] = Product(
        code=ProductCode("PAPA_FRANCESA"),
        name=ProductName("Papa Francesa"),
        category=ProductCategory.ADICIONALES,
        price=MoneyCOP(8200),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Quiero un pollo asado con adicional de papas fritas y una Cocacola 1.5",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert "1 x Papa Francesa" in result["response_text"]
    assert "1 x Coca-Cola 1.5 L" in result["response_text"]
    assert "Total acumulado: $61200" in result["response_text"]
    assert len(services.session.cart) == 3


@pytest.mark.asyncio
async def test_asado_with_only_potato_keeps_side_as_observation_without_charge() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    services.products["PAPA_FRANCESA"] = Product(
        code=ProductCode("PAPA_FRANCESA"),
        name=ProductName("Papa Francesa"),
        category=ProductCategory.ADICIONALES,
        price=MoneyCOP(8200),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="quiero un pollo asado con solo papa")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert "Papa Francesa" not in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == ["ASADO_ENTERO"]
    assert "Acompanamiento asado: solo papa." in (services.session.observations or "")


@pytest.mark.asyncio
async def test_asado_with_only_cooked_yuca_keeps_side_as_observation_without_charge() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    services.products["PAPA_SALADA"] = Product(
        code=ProductCode("PAPA_SALADA"),
        name=ProductName("Papa o yuca salada"),
        category=ProductCategory.ADICIONALES,
        price=MoneyCOP(5000),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="me regalas un asado solo con yuca cosida")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert "Papa o yuca salada" not in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == ["ASADO_ENTERO"]
    assert "Acompanamiento asado: solo yuca cocida." in (services.session.observations or "")


@pytest.mark.asyncio
async def test_asado_with_only_fried_yuca_keeps_side_as_observation_without_charge() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    services.products["YUCA_FRITA"] = Product(
        code=ProductCode("YUCA_FRITA"),
        name=ProductName("Yuca frita"),
        category=ProductCategory.ADICIONALES,
        price=MoneyCOP(5000),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="un asado sin papa y sin yuca cosida pero solo yuca frita",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert "Yuca frita" not in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == ["ASADO_ENTERO"]
    assert "Acompanamiento asado: sin papa ni yuca cocida; solo yuca frita." in (
        services.session.observations or ""
    )


@pytest.mark.asyncio
async def test_asado_with_explicit_fried_yuca_additional_still_charges_extra() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    services.products["YUCA_FRITA"] = Product(
        code=ProductCode("YUCA_FRITA"),
        name=ProductName("Yuca frita"),
        category=ProductCategory.ADICIONALES,
        price=MoneyCOP(5000),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="quiero un pollo asado con adicional de yuca frita")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert "1 x Yuca frita" in result["response_text"]
    assert "Total acumulado: $49500" in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == ["ASADO_ENTERO", "YUCA_FRITA"]


@pytest.mark.asyncio
async def test_broaster_with_generic_yuca_asks_extra_type() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="quiero medio broaster con yuca")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.ASK_SIDE_EXTRA
    assert "La yuca para broaster seria un adicional" in result["response_text"]
    assert "1. Yuca frita" in result["response_text"]
    assert "2. Papa o yuca salada" in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == ["BROASTER_MEDIO"]


@pytest.mark.asyncio
async def test_side_extra_selection_asks_quantity() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.ASK_SIDE_EXTRA)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="1")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.ASK_QUANTITY
    assert "Yuca frita" in result["response_text"]
    assert "Cuantas unidades" in result["response_text"]


@pytest.mark.asyncio
async def test_extra_sauce_asks_sauce_type() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.PRODUCT_CATEGORY)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="adicional de salsa")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.ASK_PRODUCT_VARIANT
    assert "Adicional de Salsas" in result["response_text"]
    assert "1. Tártara" in result["response_text"]
    assert "2. Ají" in result["response_text"]


@pytest.mark.asyncio
async def test_sauce_change_is_saved_as_observation_without_cost() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="quiero medio broaster con aji")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert [item.product_code.value for item in services.session.cart] == ["BROASTER_MEDIO"]
    assert "Salsas broaster solicitadas: ají." in (services.session.observations or "")
    assert "$25500" in result["response_text"]


@pytest.mark.asyncio
async def test_graph_polite_greeting_order_goes_directly_to_cart() -> None:
    services = FakeConversationServices()
    services.products["SOPA_ADICIONAL"] = Product(
        code=ProductCode("SOPA_ADICIONAL"),
        name=ProductName("Sopa Adicional"),
        category=ProductCategory.ADICIONALES,
        price=MoneyCOP(3500),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="hola buenos dias me regala medio broaster una sopa y un hit de mango",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "Bienvenido" not in result["response_text"]
    assert "1 x 1/2 Broasted" in result["response_text"]
    assert "1 x Sopa Adicional" in result["response_text"]
    assert "1 x Jugos Hit personal" in result["response_text"]
    assert len(services.session.cart) == 3


@pytest.mark.asyncio
async def test_post_add_generic_papas_fritas_adds_to_cart() -> None:
    services = FakeConversationServices()
    services.products["PAPA_FRANCESA"] = Product(
        code=ProductCode("PAPA_FRANCESA"),
        name=ProductName("Papa Francesa"),
        category=ProductCategory.ADICIONALES,
        price=MoneyCOP(8200),
    )
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="unas papas fritas tambien",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x Papa Francesa" in result["response_text"]
    assert len(services.session.cart) == 1


@pytest.mark.asyncio
async def test_confirm_order_clears_cart() -> None:
    services = FakeConversationServices()
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 2))
    services.session.customer_name = "Angel David"
    services.session.customer_phone = "3153327502"
    services.session.customer_address = "Transversal 23 #52a-21"
    services.session.customer_neighborhood = "Bosquesitos"
    services.session.payment_method = "Efectivo"
    services.session.move_to(ConversationState.CHECKOUT_REVIEW)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="si",
        cart=[
            CartLineState(
                product_code="ASADO_MEDIO",
                product_name="1/2 Asado",
                unit_price_cop=22300,
                quantity=2,
                subtotal_cop=44600,
            )
        ],
    )

    state = await nodes.confirm_order(state, services)

    assert state.current_step == ConversationState.MAIN_MENU
    assert state.cart == []
    assert services.session.cart == []
    assert len(services.synced_orders) == 1


@pytest.mark.asyncio
async def test_confirm_order_requires_payment_method() -> None:
    services = FakeConversationServices()
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    services.session.customer_name = "Angel David"
    services.session.customer_phone = "3153327502"
    services.session.customer_address = "Transversal 23 #52a-21"
    services.session.customer_neighborhood = "Bosquesitos"
    services.session.move_to(ConversationState.CHECKOUT_REVIEW)
    state = ConversationGraphState(chat_id=123, raw_text="si")

    state = await nodes.load_or_create_session(state, services)
    state = await nodes.confirm_order(state, services)

    assert state.current_step == ConversationState.ASK_CUSTOMER_DATA
    assert state.errors == ["metodo de pago"]
    assert services.session.cart
    assert services.synced_orders == []


@pytest.mark.asyncio
async def test_confirm_order_keeps_cart_when_admin_sync_fails() -> None:
    services = FakeConversationServices()
    services.fail_sync = True
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    services.session.customer_name = "Angel David"
    services.session.customer_phone = "3153327502"
    services.session.customer_address = "Transversal 23 #52a-21"
    services.session.customer_neighborhood = "Bosquesitos"
    services.session.payment_method = "Efectivo"
    services.session.move_to(ConversationState.CHECKOUT_REVIEW)
    state = ConversationGraphState(chat_id=123, raw_text="si")

    state = await nodes.load_or_create_session(state, services)
    state = await nodes.confirm_order(state, services)

    assert state.current_step == ConversationState.CHECKOUT_REVIEW
    assert "No pude registrar tu pedido" in state.response_text
    assert services.session.cart
    assert services.synced_orders == []


@pytest.mark.asyncio
async def test_confirm_order_syncs_persisted_checkout_to_admin_backend() -> None:
    services = FakeConversationServices()
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 2))
    services.session.customer_name = "Angel David"
    services.session.customer_phone = "3153327502"
    services.session.customer_address = "Transversal 23 #52a-21"
    services.session.customer_neighborhood = "Bosquesitos"
    services.session.payment_method = "Efectivo"
    services.session.move_to(ConversationState.CHECKOUT_REVIEW)
    state = ConversationGraphState(chat_id=123, raw_text="si")

    state = await nodes.load_or_create_session(state, services)
    state = await nodes.confirm_order(state, services)

    assert state.current_step == ConversationState.MAIN_MENU
    assert len(services.synced_orders) == 1
    synced = services.synced_orders[0]
    assert synced.customer.full_name == "Angel David"
    assert synced.customer.phone == "3153327502"
    assert synced.customer.address == "Transversal 23 #52a-21 - Bosquesitos"
    assert synced.payment_method == "Efectivo"
    assert synced.delivery_fee_cop == 2000
    assert [(item.product_code, item.quantity) for item in synced.items] == [("ASADO_MEDIO", 2)]
    assert services.session.customer_name is None
