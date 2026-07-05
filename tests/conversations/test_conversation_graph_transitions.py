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
        self.products = {
            "GASEOSA": Product(
                code=ProductCode("GASEOSA"),
                name=ProductName("Gaseosa"),
                category=ProductCategory.BEBIDAS,
                price=MoneyCOP(3000),
            ),
            "ASADO_MEDIO": Product(
                code=ProductCode("ASADO_MEDIO"),
                name=ProductName("1/2 Asado"),
                category=ProductCategory.POLLO_ASADO,
                price=MoneyCOP(22300),
            ),
            "BROASTER_MEDIO": Product(
                code=ProductCode("BROASTER_MEDIO"),
                name=ProductName("1/2 Broasted"),
                category=ProductCategory.POLLO_BROASTER,
                price=MoneyCOP(25500),
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

    async def sync_confirmed_order(self, payload: AdminOrderPayload) -> None:
        self.synced_orders.append(payload)


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
async def test_schedules_show_real_hours() -> None:
    services = FakeConversationServices()
    state = ConversationGraphState(chat_id=123, raw_text="4")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)
    state = await nodes.show_schedules(state, services)

    assert "Lunes a domingo" in state.response_text
    assert "11:00 a.m. a 4:00 p.m." in state.response_text
    assert "0." in state.response_text


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
        raw_text="Wendy\n3022873946\nCra 28a#195-33\nLagos 2\nNinguna",
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
    assert state.customer.payment_method == "Pendiente por confirmar"
    assert state.current_step == ConversationState.CHECKOUT_REVIEW


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
async def test_graph_adds_natural_order_items_to_cart() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    services.products["LITRO_MEDIO"] = Product(
        code=ProductCode("LITRO_MEDIO"),
        name=ProductName("Litro y Medio"),
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
    assert "1 x Litro y Medio" in result["response_text"]
    assert "Total acumulado: $53000" in result["response_text"]
    assert len(services.session.cart) == 2


@pytest.mark.asyncio
async def test_question_about_gaseosas_lists_products_without_adding_to_cart() -> None:
    services = FakeConversationServices()
    services.products["LITRO_MEDIO"] = Product(
        code=ProductCode("LITRO_MEDIO"),
        name=ProductName("Litro y Medio"),
        category=ProductCategory.BEBIDAS,
        price=MoneyCOP(8500),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Que gaseosas tienes?")

    result = await graph.ainvoke(state)

    assert "🥤 Bebidas" in result["response_text"]
    assert "Gaseosa: $3000" in result["response_text"]
    assert "Litro y Medio: $8500" in result["response_text"]
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
    services.products["LITRO_MEDIO"] = Product(
        code=ProductCode("LITRO_MEDIO"),
        name=ProductName("Litro y Medio"),
        category=ProductCategory.BEBIDAS,
        price=MoneyCOP(8500),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Cuanto vale una gaseosa?")

    result = await graph.ainvoke(state)

    assert "🥤 Bebidas" in result["response_text"]
    assert "Gaseosa: $3000" in result["response_text"]
    assert "Litro y Medio: $8500" in result["response_text"]
    assert "Gaseosa vale $3000" not in result["response_text"]
    assert len(services.session.cart) == 0


@pytest.mark.asyncio
async def test_question_about_delivery_answers_without_ai() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Domicilio para Provenza cuanto es?")

    result = await graph.ainvoke(state)

    assert "domicilio para provenza cuesta $2000" in result["response_text"].lower()
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

    assert "no cuento con informacion de ese producto" in result.response_text.lower()
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
    services.products["LITRO_MEDIO"] = Product(
        code=ProductCode("LITRO_MEDIO"),
        name=ProductName("Litro y Medio"),
        category=ProductCategory.BEBIDAS,
        price=MoneyCOP(8500),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="La 1.5?")

    result = await graph.ainvoke(state)

    assert "Litro y Medio vale $8500" in result["response_text"]
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
    services.products["LITRO_MEDIO"] = Product(
        code=ProductCode("LITRO_MEDIO"),
        name=ProductName("Litro y Medio"),
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
    assert "1 x Litro y Medio" in result["response_text"]
    assert "Total acumulado: $61200" in result["response_text"]
    assert len(services.session.cart) == 3


@pytest.mark.asyncio
async def test_graph_polite_greeting_order_goes_directly_to_cart() -> None:
    services = FakeConversationServices()
    services.products["SOPA_ADICIONAL"] = Product(
        code=ProductCode("SOPA_ADICIONAL"),
        name=ProductName("Sopa Adicional"),
        category=ProductCategory.ADICIONALES,
        price=MoneyCOP(3500),
    )
    services.products["GATORADE"] = Product(
        code=ProductCode("GATORADE"),
        name=ProductName("Gatorade"),
        category=ProductCategory.BEBIDAS,
        price=MoneyCOP(3500),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="hola buenos dias me regala medio broaster una sopa y una gatorade",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "Bienvenido" not in result["response_text"]
    assert "1 x 1/2 Broasted" in result["response_text"]
    assert "1 x Sopa Adicional" in result["response_text"]
    assert "1 x Gatorade" in result["response_text"]
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
