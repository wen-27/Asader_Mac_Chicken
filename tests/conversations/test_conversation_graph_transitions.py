"""Conversation orchestration code. It should coordinate state transitions and delegate business work to use cases/services."""

from __future__ import annotations

from datetime import date

import pytest

from app.modules.catalog.domain.enums import ProductCategory, ProductRestriction
from app.modules.catalog.domain.product import Product
from app.modules.ai.application.rule_based_order_parser import parse_natural_order_rules
from app.modules.ai.application.schemas import NaturalLanguageOrderParse, ParsedOrderItem
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
        self.ai_parsed: NaturalLanguageOrderParse | None = None
        self.ai_calls: list[str] = []
        self.unavailable_variant_codes: set[str] = set()
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
            "ICOPOR_SOPA": Product(
                code=ProductCode("ICOPOR_SOPA"),
                name=ProductName("Icopor Sopa"),
                category=ProductCategory.ADICIONALES,
                price=MoneyCOP(350),
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

    async def interpret_natural_order(self, message: str) -> NaturalLanguageOrderParse:
        self.ai_calls.append(message)
        return self.ai_parsed or parse_natural_order_rules(message)

    async def list_products_by_category(self, category: ProductCategory) -> list[Product]:
        return [
            product
            for product in self.products.values()
            if product.category == category and product.is_active
        ]

    async def find_product(self, code_or_text: str) -> Product | None:
        code = code_or_text.upper().replace(" ", "_")
        return self.products.get(code)

    async def evaluate_product_availability(
        self,
        product: Product,
        business_date,
        variant_label: str | None = None,
    ):
        variant_code = None
        if variant_label:
            normalized_variant = nodes.normalize_text(variant_label)
            if product.code.value == "ASADO_CUARTO":
                if "pierna" in normalized_variant:
                    variant_code = "ASADO_CUARTO_PIERNA"
                elif "pechuga" in normalized_variant:
                    variant_code = "ASADO_CUARTO_PECHUGA"
            elif product.code.value == "BROASTER_CUARTO":
                if "pierna" in normalized_variant:
                    variant_code = "BROASTER_CUARTO_PIERNA"
                elif "pechuga" in normalized_variant:
                    variant_code = "BROASTER_CUARTO_PECHUGA"
        is_calendar_restricted = (
            product.restricted_to == ProductRestriction.WEEKEND_OR_HOLIDAY
            and business_date.weekday() not in (5, 6)
        )
        variant_unavailable = variant_code in self.unavailable_variant_codes
        is_available = product.is_active and product.is_available and not is_calendar_restricted and not variant_unavailable
        reason = "available"
        if not product.is_active or not product.is_available or variant_unavailable:
            reason = "out_of_stock"
        elif is_calendar_restricted:
            reason = "restricted"
        return type(
            "AvailabilityResult",
            (),
            {
                "is_available": is_available,
                "product_name": product.name.value if not variant_label else f"{product.name.value} - {variant_label}",
                "alternatives": (),
                "recommended_alternative": None,
                "reason": reason,
            },
        )()

    async def calculate_delivery(self, address: str, neighborhood: str) -> CalculateDeliveryResult:
        normalized_neighborhood = nodes.normalize_text(neighborhood)
        delivery_price_cop = 2000
        if "olympo" in normalized_neighborhood or "olimpo" in normalized_neighborhood:
            delivery_price_cop = 7000
        elif "bellavista" in normalized_neighborhood:
            delivery_price_cop = 4000
        return CalculateDeliveryResult(
            found=True,
            delivery_price_cop=delivery_price_cop,
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
    assert "bienvenid" in state.response_text.lower()
    assert "Bebidas" in state.response_text
    assert "Adicionales" in state.response_text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_text",
    [
        "me muestras la carta",
        "que venden hoy",
        "quiero ver el menyu",
        "quiero pedir comida",
        "quiero ver la comda",
        "que productos tienen para almorzar",
        "quiero hacer un pedido",
    ],
)
async def test_menu_related_natural_requests_return_main_menu(raw_text: str) -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.NATURAL_ORDER)
    state = ConversationGraphState(chat_id=123, raw_text=raw_text)

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert state.intent == ConversationIntent.MOSTRAR_MENU
    assert route_after_intent(state) == "show_main_menu"


@pytest.mark.asyncio
async def test_orden_text_commands_work_from_post_add() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.POST_ADD)
    state = ConversationGraphState(chat_id=123, raw_text="quiero ver mi orden")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert state.intent == ConversationIntent.MOSTRAR_CARRITO
    assert route_after_intent(state) == "show_cart"


@pytest.mark.asyncio
async def test_repeated_punctuated_greeting_from_natural_order_returns_menu() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.NATURAL_ORDER)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Hola, buenas tardes\nHola, buenas tardes",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.MAIN_MENU
    assert "bienvenid" in result["response_text"].lower()
    assert "Bebidas" in result["response_text"]
    assert "Puedes escribirme tu pedido" not in result["response_text"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_text",
    [
        "Hola, buenas tardes",
        "¡Hola, buenos días!",
        "Muy buenas,",
        "Buenas noches!!!",
        "Buen día",
        "Holaaaa",
        "Buenasss tardes",
        "Buenas días",
        "Wenas",
        "Wenas días",
        "Buenas veci",
        "Buenas eci",
        "Saludos",
        "Hola, muy buenas tardes",
    ],
)
async def test_punctuated_accented_greetings_return_menu(raw_text: str) -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.NATURAL_ORDER)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text=raw_text)

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.MAIN_MENU
    assert "bienvenid" in result["response_text"].lower()
    assert "Puedes escribirme tu pedido" not in result["response_text"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_text", "expected_intent"),
    [
        ("  Ver,   menú!!! ", ConversationIntent.MOSTRAR_MENU),
        ("¿Me muestras el carrito?", ConversationIntent.MOSTRAR_CARRITO),
        ("Vaciar, el carrito!!!", ConversationIntent.VACIAR_CARRITO),
        ("Finalizar, pedido.", ConversationIntent.PEDIR_DATOS_CLIENTE),
        ("Horários???", ConversationIntent.HORARIOS),
    ],
)
async def test_punctuation_accents_and_spacing_do_not_break_common_intents(
    raw_text: str,
    expected_intent: ConversationIntent,
) -> None:
    services = FakeConversationServices()
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    services.session.move_to(ConversationState.POST_ADD)
    state = ConversationGraphState(chat_id=123, raw_text=raw_text)

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert state.intent == expected_intent


@pytest.mark.asyncio
async def test_real_customer_polite_order_sends_welcome_menu_and_keeps_items() -> None:
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
        raw_text="Buenas tardes me regalas porfa un pollo asado con yuca frita",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "Bienvenid@ a Mac Chicken" in result["response_text"]
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert "1 x Yuca frita" in result["response_text"]
    assert len(services.session.cart) == 2


@pytest.mark.asyncio
async def test_direct_order_from_main_menu_does_not_repeat_welcome_menu() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    services.session.move_to(ConversationState.MAIN_MENU)
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Quiero un pollo asado"))

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert "Bienvenid@ a Mac Chicken" not in result["response_text"]


@pytest.mark.asyncio
async def test_natural_order_with_customer_data_goes_to_checkout_review() -> None:
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
        raw_text=(
            "Quiero un pollo asado\n"
            "Nombre: Juan Perez\n"
            "Direccion: Cra 3 # 48-06\n"
            "Barrio: Lagos II\n"
            "Telefono: 3153327502\n"
            "Metodo de pago: efectivo"
        ),
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.CHECKOUT_REVIEW
    assert "Revisa tu orden" in result["response_text"]
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert "Cliente: Juan Perez" in result["response_text"]
    assert services.session.customer_name == "Juan Perez"
    assert len(services.session.cart) == 1


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
async def test_real_customer_two_roasted_chickens_with_sauces_is_added() -> None:
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
        raw_text="Muy buenas tardes me vendes 2 pollos asados con ají y tartara",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "Por ahora no cuento con informacion" not in result["response_text"]
    assert "2 x 1 Asado Entero" in result["response_text"]
    assert services.session.cart[0].quantity == 2
    assert [item.product_code.value for item in services.session.cart] == ["ASADO_ENTERO"]
    assert "Salsas asado solicitadas: ají, tártara." in (services.session.observations or "")


@pytest.mark.asyncio
async def test_real_customer_colaborar_two_roasted_chickens_with_sauces_is_added_directly() -> None:
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
        raw_text="Muy buenas tardes me puedes colaborar con 2 pollos asados con ají y tartara",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "Pollo asado\n\n1." not in result["response_text"]
    assert "2 x 1 Asado Entero: $89000" in result["response_text"]
    assert services.session.cart[0].quantity == 2
    assert "Salsas asado solicitadas: ají, tártara." in (services.session.observations or "")


@pytest.mark.asyncio
async def test_real_customer_colaborar_order_with_price_tail_adds_and_shows_total() -> None:
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
        raw_text="Muy buenas tardes me puedes colaborar con 2 pollos asados con ají y tartara, que valen?",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "Gracias por escribirme. No cuento con informacion" not in result["response_text"]
    assert "2 x 1 Asado Entero: $89000" in result["response_text"]
    assert "Total acumulado: $89000" in result["response_text"]


@pytest.mark.asyncio
async def test_full_order_phrase_inside_asado_menu_adds_quantity_directly() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    services.session.move_to(ConversationState.SELECT_ASADO)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Necesito 2 pollos asados con ají y tartara",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "¿Cuantas unidades deseas añadir?" not in result["response_text"]
    assert "2 x 1 Asado Entero: $89000" in result["response_text"]


@pytest.mark.asyncio
async def test_half_chicken_text_inside_asado_menu_uses_asado_context() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.SELECT_ASADO)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="quiero un medio pollo profa")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x 1/2 Asado" in result["response_text"]
    assert "Cuarto de pollo" not in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == ["ASADO_MEDIO"]


@pytest.mark.asyncio
async def test_order_with_contents_question_inside_asado_menu_does_not_ask_quantity() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    services.session.move_to(ConversationState.SELECT_ASADO)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Me regalas un pollo asado, con que viene? Trae sopa?")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "¿Cuantas unidades deseas añadir?" not in result["response_text"]
    assert "1 x 1 Asado Entero: $44500" in result["response_text"]
    assert "Sopa Adicional" not in result["response_text"]
    assert "papa" in result["response_text"].lower()
    assert "yuca cocida" in result["response_text"].lower()
    assert "ají" in result["response_text"]
    assert "incluye 2 sopas sin costo" in result["response_text"].lower()
    assert len(services.session.cart) == 1


@pytest.mark.asyncio
async def test_graph_uses_ai_interpreter_when_rules_do_not_understand_human_order() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    services.ai_parsed = NaturalLanguageOrderParse(
        intent="order_items",
        items=[ParsedOrderItem(code="ASADO_ENTERO", quantity=2)],
        confidence=0.91,
        notes=["llm_fallback"],
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="veci me provocan dos pollos doraditos de esos de la casa",
    )

    result = await graph.ainvoke(state)

    assert services.ai_calls == ["veci me provocan dos pollos doraditos de esos de la casa"]
    assert result["current_step"] == ConversationState.ASK_CHICKEN_STYLE
    assert "¿Lo quieres asado o broster?" in result["response_text"]
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_unstyled_chickens_with_incomplete_bodega_destination_asks_style_first() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(
        ConversationGraphState(chat_id=123, raw_text="Ban día vesi me vende 3 pollos para la bodega 18")
    )

    assert result["current_step"] == ConversationState.ASK_CHICKEN_STYLE
    assert "¿Lo quieres asado o broster?" in result["response_text"]
    assert "domicilio" not in result["response_text"].lower()
    assert services.session.observations == "para la bodega 18"
    assert services.session.customer_address is None
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_unstyled_chickens_with_bodega_destination_adds_quantity_after_style() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    graph = build_conversation_graph(services)

    await graph.ainvoke(
        ConversationGraphState(chat_id=123, raw_text="Ban día vesi me vende 3 pollos para la bodega 18")
    )
    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="asado"))

    assert result["current_step"] == ConversationState.POST_ADD
    assert "3 x 1 Asado Entero" in result["response_text"]
    assert "Nombre completo" in result["response_text"]
    assert "Nota o especificacion (opcional)" in result["response_text"]
    assert services.session.observations == "para la bodega 18"
    assert services.session.customer_address is None
    assert len(services.session.cart) == 1
    assert services.session.cart[0].quantity == 3


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
async def test_real_customer_service_question_gets_warm_answer() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Muy buenas tardes tiene servicio?")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.MAIN_MENU
    assert "si claro, contamos con servicio" in result["response_text"]
    assert "dime como te puedo ayudar" in result["response_text"].lower()
    assert "Puedes escribirme tu pedido en texto normal" not in result["response_text"]


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
        assert state.query_type == "availability"
        assert state.query_value == "maduro con queso"
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
    assert "Cancele la orden actual" in result["response_text"]
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
    assert "Cancele la orden actual" in result["response_text"]
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
    assert "vacie tu orden" in state.response_text


@pytest.mark.asyncio
async def test_natural_clear_my_cart_command_clears_cart() -> None:
    services = FakeConversationServices()
    services.session.add_cart_item(cart_item_from_product(services.products["ASADO_MEDIO"], 1))
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Quiero vaciar mi carrito"))

    assert result["current_step"] == ConversationState.MAIN_MENU
    assert services.session.cart == []
    assert "vacie tu orden" in result["response_text"]


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
    assert "Lasagna Mixta solo esta disponible fines de semana" in state.response_text
    assert "Selecciona menu" in state.response_text
    assert "no cuento con informacion" not in state.response_text.lower()


@pytest.mark.asyncio
async def test_natural_language_fallback_explains_how_to_open_menu() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="asdfasdf pollo nose"))

    assert "Puedes escribirme tu orden en texto normal" in result["response_text"]
    assert "escribe menu" in result["response_text"].lower()
    assert "quiero ver el menu" in result["response_text"].lower()
    assert "horarios" in result["response_text"].lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_text", "expected"),
    [
        ("Ola veci", "Bienvenid@ a Mac Chicken"),
        ("Hola buena tarde", "Bienvenid@ a Mac Chicken"),
        ("Buen día veci hágame favor", "Bienvenid@ a Mac Chicken"),
        ("Tienes servicio", "servicio a domicilio"),
        ("Ya tienes servicio", "servicio a domicilio"),
        ("Veci para pedir un servicio", "servicio a domicilio"),
        ("Recibes nequi?", "La cuenta de Nequi"),
        ("Tienen llave para transferir?", "La cuenta de Nequi"),
        ("Me ayudas con el número para transferir", "La cuenta de Nequi"),
        ("En cuanto lo traen", "40 minutos"),
        ("Se demora?, debo salir a la 1", "40 minutos"),
        ("Ustedes me dice si ya está paso en 15 minutos", "40 minutos"),
        ("Buenas tardes que precio tiene el pollo azado", "Pollo asado"),
        ("Veci tiene pollo", "Pollo asado"),
        ("Cuanto vale el domi?", "servicio a domicilio"),
        ("Pollo asado", "Pollo asado"),
        ("Listo pollo broaster", "Pollo broaster"),
    ],
)
async def test_qa_history_common_messages_do_not_fall_back(raw_text: str, expected: str) -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text=raw_text))

    assert expected in result["response_text"]
    assert "Puedes escribirme tu orden en texto normal" not in result["response_text"]
    assert "no cuento con informacion" not in result["response_text"].lower()


@pytest.mark.asyncio
async def test_qa_history_total_question_with_cart_shows_cart() -> None:
    services = FakeConversationServices()
    services.session.add_cart_item(cart_item_from_product(services.products["BROASTER_ENTERO"], 1))
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Cuanto seria todo veci?"))

    assert "Tu orden" in result["response_text"]
    assert "Broasted Entero" in result["response_text"]
    assert "Total" in result["response_text"]
    assert "no cuento con informacion" not in result["response_text"].lower()


@pytest.mark.asyncio
async def test_qa_history_numeric_brostee_order_adds_whole_broaster() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="1 pollo a la brostee"))

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x Broasted Entero" in result["response_text"]
    assert "Puedes escribirme tu orden en texto normal" not in result["response_text"]


@pytest.mark.asyncio
async def test_qa_history_cart_accepts_checkout_fragments_from_natural_order_state() -> None:
    services = FakeConversationServices()
    services.session.add_cart_item(cart_item_from_product(services.products["BROASTER_MEDIO"], 1))
    services.session.move_to(ConversationState.NATURAL_ORDER)
    graph = build_conversation_graph(services)

    address = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Cll 40 #6-31"))
    neighborhood = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Lagos 2"))
    name = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="A nombre de Gabriela"))
    payment = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Pagamos por enqui"))

    assert "Puedes escribirme tu orden en texto normal" not in address["response_text"]
    assert "Puedes escribirme tu orden en texto normal" not in neighborhood["response_text"]
    assert "Puedes escribirme tu orden en texto normal" not in name["response_text"]
    assert "Puedes escribirme tu orden en texto normal" not in payment["response_text"]
    assert services.session.customer_address == "Cll 40 #6-31"
    assert services.session.customer_neighborhood == "Lagos 2"
    assert services.session.customer_name == "Gabriela"
    assert services.session.payment_method == "Nequi"


@pytest.mark.asyncio
async def test_checkout_fragment_strips_order_text_before_embedded_address() -> None:
    services = FakeConversationServices()
    services.session.add_cart_item(cart_item_from_product(services.products["ASADO_MEDIO"], 1))
    services.session.move_to(ConversationState.NATURAL_ORDER)
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(
        ConversationGraphState(chat_id=123, raw_text="Buenos días necesito un pollo a la cra28a#195-33")
    )

    assert "barrio" in result["response_text"]
    assert services.session.customer_address == "cra28a#195-33"
    assert "Buenos días necesito un pollo" not in services.session.customer_address


@pytest.mark.asyncio
async def test_qa_history_para_llevar_with_cart_switches_to_pickup_data() -> None:
    services = FakeConversationServices()
    services.session.add_cart_item(cart_item_from_product(services.products["ASADO_MEDIO"], 1))
    services.session.move_to(ConversationState.NATURAL_ORDER)
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Para llevar"))

    assert result["current_step"] == ConversationState.ASK_CUSTOMER_DATA
    assert result["fulfillment_type"] == "PICKUP"
    assert "orden lista para recoger" in result["response_text"]
    assert "Puedes escribirme tu orden en texto normal" not in result["response_text"]


@pytest.mark.asyncio
async def test_qa_history_loose_ready_reply_with_cart_starts_checkout() -> None:
    services = FakeConversationServices()
    services.session.add_cart_item(cart_item_from_product(services.products["ASADO_MEDIO"], 1))
    services.session.move_to(ConversationState.NATURAL_ORDER)
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="listo"))

    assert result["current_step"] == ConversationState.ASK_CUSTOMER_DATA
    assert "Para finalizar tu orden necesito los datos de envio" in result["response_text"]
    assert "Puedes escribirme tu orden en texto normal" not in result["response_text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["?", "Me confirmas porfis"])
async def test_qa_history_cart_review_requests_show_cart_instead_of_fallback(message: str) -> None:
    services = FakeConversationServices()
    services.session.add_cart_item(cart_item_from_product(services.products["BROASTER_ENTERO"], 1))
    services.session.move_to(ConversationState.NATURAL_ORDER)
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text=message))

    assert "Tu orden" in result["response_text"]
    assert "Broasted Entero" in result["response_text"]
    assert "Puedes escribirme tu orden en texto normal" not in result["response_text"]


@pytest.mark.asyncio
async def test_qa_history_chicken_piece_question_answers_contents() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="El cuarto es una presa o dos?"))

    assert "Puedes escribirme tu orden en texto normal" not in result["response_text"]
    assert "No cuento con informacion" not in result["response_text"]
    assert "incluye" in result["response_text"].lower() or "trae" in result["response_text"].lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["Ok", "Porfa", "Si por favor", "Vale muchas gracias"])
async def test_qa_history_short_polite_replies_do_not_fall_back(message: str) -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text=message))

    assert result["response_text"]
    assert "Puedes escribirme tu orden en texto normal" not in result["response_text"]


@pytest.mark.asyncio
async def test_qa_history_other_phone_order_does_not_fall_back() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Ya estamos pidiendo por otro celular"))

    assert "Cancele la orden actual" in result["response_text"]
    assert "Puedes escribirme tu orden en texto normal" not in result["response_text"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "Avenida Bucarica Bloque 5-2 apto 302",
        "Para altos de Bellavista sector 3 bloque uno apartamento 504",
        "#5-54",
        "Bucarica",
    ],
)
async def test_qa_history_loose_delivery_data_without_cart_starts_delivery(message: str) -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text=message))

    assert "domicilio" in result["response_text"].lower()
    assert "Puedes escribirme tu orden en texto normal" not in result["response_text"]


@pytest.mark.asyncio
async def test_qa_history_total_question_without_cart_shows_empty_cart() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Cuanto seria todo"))

    assert "orden esta vacia" in result["response_text"].lower()
    assert "Puedes escribirme tu orden en texto normal" not in result["response_text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["Pechuga", "Pierna si me hace el favor"])
async def test_qa_history_loose_chicken_part_followup_does_not_fall_back(message: str) -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text=message))

    assert "Puedes escribirme tu orden en texto normal" not in result["response_text"]
    assert "producto quieres saber" in result["response_text"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Me confirmas por favor", "orden esta vacia"),
        ("Me das el precio por favor", "Elige una categoria"),
        ("Puedo pagar allá con tarjeta?", "Datafono"),
        ("Es el de lagos cierto", "servicio a domicilio"),
        ("En cuanto puedo pasar", "40 minutos"),
        ("Hola necesito saber si me van a mandar mí pedido gracias", "40 minutos"),
        ("El ají porfa si échame unos cuantos", "salsas"),
        ("Esta a nombre de fab leo per", "domicilio"),
    ],
)
async def test_qa_history_misc_real_messages_do_not_fall_back(message: str, expected: str) -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text=message))

    assert expected in result["response_text"]
    assert "Puedes escribirme tu orden en texto normal" not in result["response_text"]


@pytest.mark.asyncio
async def test_qa_history_quarter_part_without_style_asks_chicken_style() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Pero q los dos cuartos sean pechuga"))

    assert "Pollo asado" in result["response_text"]
    assert "Pollo broaster" in result["response_text"]
    assert "Puedes escribirme tu orden en texto normal" not in result["response_text"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("...", "Con mucho gusto"),
        ("👆", "Con mucho gusto"),
        ("Raul", "domicilio"),
        ("Dice que 8 mil", "Bienvenid@ a Mac Chicken"),
        ("Dos", "Bienvenid@ a Mac Chicken"),
        ("Eso es a qui en Lagos verdad ?", "servicio a domicilio"),
        ("Listo pago con un billete de 100 mil", "Efectivo"),
    ],
)
async def test_qa_history_last_resort_real_messages_do_not_fall_back(message: str, expected: str) -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text=message))

    assert expected in result["response_text"]
    assert "Puedes escribirme tu orden en texto normal" not in result["response_text"]


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
    assert "Bebidas" in state.response_text


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
async def test_empty_category_keeps_user_in_categories_so_next_number_has_exit() -> None:
    services = FakeConversationServices()
    for product in services.products.values():
        if product.category == ProductCategory.ESPECIALES:
            product.is_active = False
    services.session.move_to(ConversationState.PRODUCT_CATEGORY)
    graph = build_conversation_graph(services)

    first_result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="5"))

    assert first_result["current_step"] == ConversationState.PRODUCT_CATEGORY
    assert "Por ahora no hay productos disponibles" in first_result["response_text"]
    assert "Puedes elegir otra categoria" in first_result["response_text"]

    second_result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="1"))

    assert second_result["current_step"] == ConversationState.SELECT_ASADO
    assert "🍗 Pollo asado" in second_result["response_text"]
    assert "No encontre ese producto" not in second_result["response_text"]


@pytest.mark.asyncio
async def test_specials_menu_shows_enabled_lasagna_and_maduro() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.PRODUCT_CATEGORY)
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="5"))

    assert result["current_step"] == ConversationState.SELECT_ESPECIAL
    assert "Lasagna Mixta - $20000" in result["response_text"]
    assert "Maduro con Queso - $9500" in result["response_text"]
    assert "Por ahora no hay productos disponibles" not in result["response_text"]


@pytest.mark.asyncio
async def test_weekday_maduro_request_is_visible_but_not_available(monkeypatch) -> None:
    monkeypatch.setattr(nodes, "_business_today", lambda: date(2026, 7, 1))
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    menu_result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="platos especiales"))

    assert "Bienvenid@ a Mac Chicken" in menu_result["response_text"]

    order_result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="quiero un maduro con queso"))

    assert "Maduro con Queso solo esta disponible fines de semana" in order_result["response_text"]
    assert "Selecciona menu" in order_result["response_text"]
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_disabled_specials_still_show_in_menu_but_cannot_be_added() -> None:
    services = FakeConversationServices()
    services.products["LASAGNA_MIXTA"].is_available = False
    services.products["MADURO_QUESO"].is_available = False
    services.session.move_to(ConversationState.PRODUCT_CATEGORY)
    graph = build_conversation_graph(services)

    menu_result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="5"))

    assert menu_result["current_step"] == ConversationState.SELECT_ESPECIAL
    assert "Lasagna Mixta - $20000" in menu_result["response_text"]
    assert "Maduro con Queso - $9500" in menu_result["response_text"]

    order_result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="1"))

    assert "En este momento no tenemos Lasagna Mixta disponible" in order_result["response_text"]
    assert "Selecciona menu" in order_result["response_text"]
    assert services.session.cart == []


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

    result = await build_conversation_graph(services).ainvoke(
        ConversationGraphState(chat_id=123, raw_text="quiero una lasagna")
    )

    assert result["current_step"] == ConversationState.SELECT_ESPECIAL
    assert "Lasagna Mixta solo esta disponible fines de semana" in result["response_text"]
    assert "Selecciona menu" in result["response_text"]
    assert services.session.cart == []


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
async def test_non_chicken_products_do_not_reuse_previous_chicken_part() -> None:
    services = FakeConversationServices()
    services.products["COCA_COLA_15"] = Product(
        code=ProductCode("COCA_COLA_15"),
        name=ProductName("Coca-Cola 1.5 L"),
        category=ProductCategory.BEBIDAS,
        price=MoneyCOP(8500),
    )
    services.session.selected_product_code = ProductCode("COCA_COLA_15")
    services.session.selected_chicken_part = "Pechuga"
    services.session.move_to(ConversationState.ASK_QUANTITY)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="1",
        normalized_text="1",
        current_step=ConversationState.ASK_QUANTITY,
        selected_product_code="COCA_COLA_15",
        quantity=1,
    )

    state = await nodes.add_to_cart(state, services)

    assert state.current_step == ConversationState.POST_ADD
    assert state.cart[0].product_name == "Coca-Cola 1.5 L"
    assert "Pechuga" not in state.response_text
    assert services.session.cart[0].product_name == ProductName("Coca-Cola 1.5 L")
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
    assert "Me faltan definir" not in state.response_text
    assert "Ejemplos:" not in state.response_text
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_single_pending_quarter_response_adds_mixed_order_without_quantity_prompt() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    first = await graph.ainvoke(
        ConversationGraphState(
            chat_id=123,
            raw_text="Quiero un cuarto de pollo broster y medio asado",
        )
    )
    assert first["current_step"] == ConversationState.ASK_CHICKEN_PART
    assert "¿Lo quieres en pierna o pechuga?" in first["response_text"]
    assert "Me faltan definir" not in first["response_text"]

    second = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="pechuga"))

    assert second["current_step"] == ConversationState.POST_ADD
    assert "1 x 1/4 Broasted - Pechuga" in second["response_text"]
    assert "1 x 1/2 Asado" in second["response_text"]
    assert sorted(item.product_name.value for item in services.session.cart) == [
        "1/2 Asado",
        "1/4 Broasted - Pechuga",
    ]


@pytest.mark.asyncio
async def test_pending_quarter_respects_unavailable_selected_part_before_adding_to_cart() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    services.unavailable_variant_codes.add("BROASTER_CUARTO_PIERNA")
    graph = build_conversation_graph(services)

    first = await graph.ainvoke(
        ConversationGraphState(
            chat_id=123,
            raw_text="Está bien me regala 2 pollos asados y un cuarto broster porfa",
        )
    )
    assert first["current_step"] == ConversationState.ASK_CHICKEN_PART
    assert "pierna o pechuga" in first["response_text"]

    second = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="1"))

    assert second["current_step"] == ConversationState.POST_ADD
    assert [item.product_code.value for item in services.session.cart] == ["ASADO_ENTERO"]
    assert services.session.cart[0].quantity == 2
    assert "2 x 1 Asado Entero" in second["response_text"]
    assert "1 x 1/4 Broasted - Pierna" not in second["response_text"]
    assert "1/4 Broasted - Pierna" in second["response_text"]
    assert "no esta disponible" in second["response_text"]


@pytest.mark.asyncio
async def test_single_pending_quarter_greeting_clears_stuck_pending_order() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    await graph.ainvoke(
        ConversationGraphState(
            chat_id=123,
            raw_text="Quiero un cuarto de pollo broster y medio asado",
        )
    )
    greeting = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Hola"))
    assert greeting["current_step"] == ConversationState.MAIN_MENU
    assert "Bienvenid@ a Mac Chicken" in greeting["response_text"]
    assert "Me faltan definir" not in greeting["response_text"]
    assert services.session.pending_order_json is None


@pytest.mark.asyncio
async def test_ambiguous_plain_chicken_pending_can_be_exited_with_zero_or_greeting() -> None:
    services = FakeConversationServices()
    services.session.pending_order_json = {
        "items": [{"code": "ASADO_CUARTO", "quantity": 1}],
        "current_index": 0,
        "allocations": [],
        "awaiting_part": None,
        "awaiting_style": True,
        "original_text": "dame un pollo",
    }
    services.session.move_to(ConversationState.ASK_CHICKEN_STYLE)
    graph = build_conversation_graph(services)

    escaped = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="0"))
    assert escaped["current_step"] == ConversationState.MAIN_MENU
    assert "Bienvenid@ a Mac Chicken" in escaped["response_text"]
    assert services.session.pending_order_json is None

    services.session.pending_order_json = {
        "items": [{"code": "ASADO_CUARTO", "quantity": 1}],
        "current_index": 0,
        "allocations": [],
        "awaiting_part": None,
        "awaiting_style": True,
        "original_text": "dame un pollo",
    }
    services.session.move_to(ConversationState.ASK_CHICKEN_STYLE)
    greeting = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="buena vcei"))
    assert greeting["current_step"] == ConversationState.MAIN_MENU
    assert "Bienvenid@ a Mac Chicken" in greeting["response_text"]
    assert services.session.pending_order_json is None


@pytest.mark.asyncio
async def test_pending_chicken_style_accepts_replacement_order_instead_of_repeating_quarter_prompt() -> None:
    services = FakeConversationServices()
    services.session.pending_order_json = {
        "items": [{"code": "ASADO_CUARTO", "quantity": 1}],
        "current_index": 0,
        "allocations": [],
        "awaiting_part": None,
        "awaiting_style": True,
        "original_text": "dame un pollo",
    }
    services.session.move_to(ConversationState.ASK_CHICKEN_STYLE)
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="era medio pollo"))

    assert result["current_step"] == ConversationState.ASK_CHICKEN_STYLE
    assert "Medio pollo" in result["response_text"]
    assert "Cuarto de pollo" not in result["response_text"]
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_pending_chicken_style_gibberish_clears_pending_instead_of_repeating_prompt() -> None:
    services = FakeConversationServices()
    services.session.pending_order_json = {
        "items": [{"code": "ASADO_CUARTO", "quantity": 1}],
        "current_index": 0,
        "allocations": [],
        "awaiting_part": None,
        "awaiting_style": True,
        "original_text": "dame un pollo",
    }
    services.session.move_to(ConversationState.ASK_CHICKEN_STYLE)
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(
        ConversationGraphState(chat_id=123, raw_text="ljajcvkj nbngfbngfbnsbnsrbnrtgnerigeribgiebvisbsrtbgsrbgsr")
    )

    assert result["current_step"] == ConversationState.MAIN_MENU
    assert "Bienvenid@ a Mac Chicken" in result["response_text"]
    assert "Cuarto de pollo" not in result["response_text"]
    assert services.session.pending_order_json is None


@pytest.mark.asyncio
async def test_pending_four_quarters_accepts_quantity_and_part_in_one_message() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    first = await graph.ainvoke(
        ConversationGraphState(chat_id=123, raw_text="quiero 4 cuartos de pollo asado")
    )
    assert first["current_step"] == ConversationState.ASK_CHICKEN_PART
    assert "Me faltan definir 4 cuarto" in first["response_text"]

    final = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="4 piernas"))

    assert final["current_step"] == ConversationState.POST_ADD
    assert "4 x 1/4 Asado - Pierna" in final["response_text"]
    assert len(services.session.cart) == 1
    assert services.session.cart[0].quantity == 4


@pytest.mark.asyncio
async def test_pending_five_quarters_accepts_mixed_distribution_in_one_message() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    first = await graph.ainvoke(
        ConversationGraphState(chat_id=123, raw_text="quiero 5 cuartos de pollo asado")
    )
    assert first["current_step"] == ConversationState.ASK_CHICKEN_PART
    assert "Me faltan definir 5 cuarto" in first["response_text"]

    final = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="4 piernas y una pechuga"))

    assert final["current_step"] == ConversationState.POST_ADD
    assert "4 x 1/4 Asado - Pierna" in final["response_text"]
    assert "1 x 1/4 Asado - Pechuga" in final["response_text"]
    assert [item.quantity for item in services.session.cart] == [4, 1]


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
async def test_ambiguous_quarter_with_part_asks_style_before_adding() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    first = await graph.ainvoke(
        ConversationGraphState(
            chat_id=123,
            raw_text="Quiero un cuarto d pollo pierna y medio asado",
        )
    )

    assert first["current_step"] == ConversationState.ASK_CHICKEN_STYLE
    assert "¿Lo quieres asado o broster?" in first["response_text"]
    assert services.session.cart == []

    second = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="broster"))

    assert second["current_step"] == ConversationState.POST_ADD
    assert "1 x 1/4 Broasted - Pierna" in second["response_text"]
    assert "1 x 1/2 Asado" in second["response_text"]
    assert [item.product_code.value for item in services.session.cart] == [
        "ASADO_MEDIO",
        "BROASTER_CUARTO",
    ]
    assert services.session.cart[0].product_name == ProductName("1/2 Asado")
    assert services.session.cart[1].product_name == ProductName("1/4 Broasted - Pierna")


@pytest.mark.asyncio
async def test_part_applies_only_to_matching_quarter_segment() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    await graph.ainvoke(
        ConversationGraphState(
            chat_id=123,
            raw_text="Quiero un cuarto d pollo pierna y medio asado",
        )
    )
    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="broster"))

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x 1/2 Asado: $22300" in result["response_text"]
    assert "1 x 1/2 Asado - Pierna" not in result["response_text"]
    assert [item.product_name.value for item in services.session.cart] == [
        "1/2 Asado",
        "1/4 Broasted - Pierna",
    ]


@pytest.mark.asyncio
async def test_ambiguous_quarter_asks_style_then_part_without_looping() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    first = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="quiero un cuarto de pollo"))
    assert first["current_step"] == ConversationState.ASK_CHICKEN_STYLE
    assert "¿Lo quieres asado o broster?" in first["response_text"]

    second = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="2"))
    assert second["current_step"] == ConversationState.ASK_CHICKEN_PART
    assert "¿Lo quieres en pierna o pechuga?" in second["response_text"]

    third = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="1"))
    assert third["current_step"] == ConversationState.POST_ADD
    assert "1 x 1/4 Broasted - Pierna" in third["response_text"]


@pytest.mark.asyncio
async def test_ambiguous_whole_chicken_asks_style_before_adding() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    graph = build_conversation_graph(services)

    first = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="quiero un pollo entero"))
    assert first["current_step"] == ConversationState.ASK_CHICKEN_STYLE
    assert "¿Lo quieres asado o broster?" in first["response_text"]

    second = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="asado"))
    assert second["current_step"] == ConversationState.POST_ADD
    assert "1 x 1 Asado Entero" in second["response_text"]


@pytest.mark.asyncio
async def test_ambiguous_half_chicken_asks_style_before_adding() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    first = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="quiero medio pollo"))
    assert first["current_step"] == ConversationState.ASK_CHICKEN_STYLE
    assert "¿Lo quieres asado o broster?" in first["response_text"]

    second = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="broster"))
    assert second["current_step"] == ConversationState.POST_ADD
    assert "1 x 1/2 Broasted" in second["response_text"]


@pytest.mark.asyncio
async def test_ambiguous_three_quarter_chicken_asks_style_then_composition() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    first = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="quiero tres cuartos de pollo"))
    assert first["current_step"] == ConversationState.ASK_CHICKEN_STYLE
    assert "¿Lo quieres asado o broster?" in first["response_text"]

    second = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="asado"))
    assert second["current_step"] == ConversationState.ASK_CHICKEN_PART
    assert "2 piernas y 1 pechuga" in second["response_text"]
    assert "2 pechugas y 1 pierna" in second["response_text"]

    third = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="2 pechugas y una pierna"))
    assert third["current_step"] == ConversationState.POST_ADD
    assert "1 x 3/4 Asado - 2 pechugas y 1 pierna" in third["response_text"]


@pytest.mark.asyncio
async def test_corrects_existing_quarter_style_and_keeps_part() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    await graph.ainvoke(
        ConversationGraphState(chat_id=123, raw_text="quiero un cuarto asado pierna y medio asado")
    )

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="No el cuarto es broster"))

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1/4 Broasted - Pierna" in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == [
        "ASADO_MEDIO",
        "BROASTER_CUARTO",
    ]
    assert services.session.cart[1].product_name == ProductName("1/4 Broasted - Pierna")


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
    assert "¿Cuantas unidades deseas añadir?" in state.response_text


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
    assert "¿Cuantas unidades deseas añadir?" in second["response_text"]
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
    assert "1. Añadir más productos" in state.response_text
    assert "3. Finalizar orden" in state.response_text


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
async def test_post_add_pickup_request_asks_for_pickup_customer_data() -> None:
    services = FakeConversationServices()
    services.session.add_cart_item(cart_item_from_product(services.products["ASADO_MEDIO"], 1))
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Es para recoger"))

    assert result["current_step"] == ConversationState.ASK_CUSTOMER_DATA
    assert result["fulfillment_type"] == "PICKUP"
    assert "orden lista para recoger" in result["response_text"]
    assert "Nombre completo" in result["response_text"]
    assert "Telefono" in result["response_text"]
    assert "Direccion" not in result["response_text"]
    assert services.session.fulfillment_type == "PICKUP"


@pytest.mark.asyncio
async def test_post_add_finalize_keeps_delivery_form_even_with_stale_pickup_session() -> None:
    services = FakeConversationServices()
    services.session.add_cart_item(cart_item_from_product(services.products["ASADO_MEDIO"], 1))
    services.session.fulfillment_type = "PICKUP"
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="3"))

    assert result["current_step"] == ConversationState.ASK_CUSTOMER_DATA
    assert result["fulfillment_type"] == "DELIVERY"
    assert "datos de envio" in result["response_text"]
    assert "Direccion" in result["response_text"]
    assert "Barrio" in result["response_text"]
    assert "orden lista para recoger" not in result["response_text"]
    assert services.session.fulfillment_type == "DELIVERY"


@pytest.mark.asyncio
async def test_post_add_accepts_direct_address_instead_of_falling_back_to_natural_order_help() -> None:
    services = FakeConversationServices()
    services.session.add_cart_item(cart_item_from_product(services.products["ASADO_MEDIO"], 1))
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(
        ConversationGraphState(
            chat_id=123,
            raw_text="Carrera 9 no 7 17 Floridablanca casco antiguo diagonal al banco dé Bogotá veterinaria Alma-vet",
        )
    )

    assert result["current_step"] == ConversationState.ASK_CUSTOMER_DATA
    assert "Me falta esta informacion" in result["response_text"]
    assert "nombre" in result["response_text"].lower()
    assert "telefono" in result["response_text"].lower()
    assert "metodo de pago" in result["response_text"].lower()
    assert "barrio" not in result["response_text"].lower()
    assert "Puedes escribirme tu pedido" not in result["response_text"]
    assert services.session.customer_address == "Carrera 9 no 7 17"
    assert services.session.customer_neighborhood == "Floridablanca casco antiguo"
    assert services.session.observations == "diagonal al banco dé Bogotá veterinaria Alma-vet"


@pytest.mark.asyncio
async def test_post_add_asks_for_complete_address_on_bodega_reference() -> None:
    services = FakeConversationServices()
    services.session.add_cart_item(cart_item_from_product(services.products["BROASTER_CUARTO"], 1))
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="para la bodega 18"))

    assert result["current_step"] == ConversationState.ASK_CUSTOMER_DATA
    assert "Me falta esta informacion" in result["response_text"]
    assert "direccion completa" in result["response_text"].lower()
    assert "calle/carrera" in result["response_text"].lower()
    assert "Puedes escribirme tu orden" not in result["response_text"]
    assert services.session.customer_address is None
    assert services.session.observations is None


@pytest.mark.asyncio
async def test_post_add_extracts_barrio_payment_and_cleans_noisy_name_from_single_line() -> None:
    services = FakeConversationServices()
    services.session.add_cart_item(cart_item_from_product(services.products["ASADO_MEDIO"], 1))
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(
        ConversationGraphState(
            chat_id=123,
            raw_text=(
                "perri hijuueputa Ángel david pinzon serrano, 3153327502, "
                "Carrera 28a numero 195 -33, el manantial efectivo"
            ),
        )
    )

    assert result["current_step"] == ConversationState.CHECKOUT_REVIEW
    assert "Datos recibidos" in result["response_text"]
    assert "Cliente: Ángel david pinzon serrano" in result["response_text"]
    assert "Barrio: el manantial" in result["response_text"]
    assert "Pago: Efectivo" in result["response_text"]
    assert services.session.customer_name == "Ángel david pinzon serrano"
    assert services.session.customer_neighborhood == "el manantial"
    assert services.session.payment_method == "Efectivo"


@pytest.mark.asyncio
async def test_new_checkout_clears_stale_customer_data_and_keeps_asking_for_neighborhood() -> None:
    services = FakeConversationServices()
    services.session.add_cart_item(cart_item_from_product(services.products["ASADO_MEDIO"], 1))
    services.session.customer_name = "Es para domicilio"
    services.session.customer_neighborhood = "Me puedes añadir 3 asados con tartara y aji porfa"
    services.session.payment_method = "Nequi"
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)

    start = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="3"))
    assert start["current_step"] == ConversationState.ASK_CUSTOMER_DATA
    assert start["fulfillment_type"] == "DELIVERY"

    after_name = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Wendy"))
    assert "telefono" in after_name["response_text"]
    assert "direccion" in after_name["response_text"]
    assert "barrio" in after_name["response_text"]
    assert "metodo de pago" in after_name["response_text"]

    after_phone = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="3022873964"))
    assert "direccion" in after_phone["response_text"]
    assert "barrio" in after_phone["response_text"]
    assert "metodo de pago" in after_phone["response_text"]

    after_address = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Cra28a#195-33"))
    assert "barrio" in after_address["response_text"]
    assert "metodo de pago" in after_address["response_text"]

    after_payment = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Nequi"))
    assert after_payment["current_step"] == ConversationState.ASK_CUSTOMER_DATA
    assert "barrio" in after_payment["response_text"]
    assert "Datos recibidos" not in after_payment["response_text"]
    assert services.session.customer_neighborhood is None


@pytest.mark.asyncio
async def test_checkout_ignores_invalid_phone_only_lines_instead_of_using_them_as_neighborhood() -> None:
    services = FakeConversationServices()
    services.session.add_cart_item(cart_item_from_product(services.products["ASADO_MEDIO"], 3))
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)

    await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="3"))
    await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Wendy"))

    invalid_phone = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="30283829299"))
    assert "telefono" in invalid_phone["response_text"]
    assert "barrio" in invalid_phone["response_text"]
    assert services.session.customer_neighborhood is None

    await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Calle 36 # 28 - 45"))

    invalid_second_number = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="293837290238"))
    assert "telefono" in invalid_second_number["response_text"]
    assert "barrio" in invalid_second_number["response_text"]
    assert services.session.customer_neighborhood is None
    assert services.session.observations is None

    await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="3022873946"))
    after_payment = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Efectivo"))

    assert after_payment["current_step"] == ConversationState.ASK_CUSTOMER_DATA
    assert "barrio" in after_payment["response_text"]
    assert "Datos recibidos" not in after_payment["response_text"]
    assert services.session.customer_neighborhood is None
    assert services.session.observations is None


@pytest.mark.asyncio
async def test_customer_data_step_pickup_request_switches_to_pickup_prompt() -> None:
    services = FakeConversationServices()
    services.session.add_cart_item(cart_item_from_product(services.products["BROASTER_ENTERO"], 1))
    services.session.fulfillment_type = "DELIVERY"
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Es para recoger"))

    assert result["current_step"] == ConversationState.ASK_CUSTOMER_DATA
    assert result["fulfillment_type"] == "PICKUP"
    assert "orden lista para recoger" in result["response_text"]
    assert "Direccion" not in result["response_text"]
    assert services.session.fulfillment_type == "PICKUP"


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
    assert "Selecciona SI" in state.response_text


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
async def test_customer_data_extracts_embedded_neighborhood_and_delivery_note_from_rich_address() -> None:
    services = FakeConversationServices()
    services.session.add_cart_item(cart_item_from_product(services.products["ASADO_MEDIO"], 1))
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(
        ConversationGraphState(
            chat_id=123,
            raw_text=(
                "Martin Andrés Flórez\n"
                "3142199149\n"
                "Carrera 9 no 7 17 Floridablanca casco antiguo diagonal al banco dé Bogotá veterinaria Alma-vet\n"
                "Efectivo\n"
                "El pedido para las 12 dé dia"
            ),
        )
    )

    assert result["current_step"] == ConversationState.CHECKOUT_REVIEW
    assert "Datos recibidos" in result["response_text"]
    assert "Cliente: Martin Andrés Flórez" in result["response_text"]
    assert "Direccion: Carrera 9 no 7 17" in result["response_text"]
    assert "Barrio: Floridablanca casco antiguo" in result["response_text"]
    assert "Barrio: El pedido para las 12" not in result["response_text"]
    assert "diagonal al banco dé Bogotá veterinaria Alma-vet" in result["response_text"]
    assert "El pedido para las 12 dé dia" in result["response_text"]
    assert services.session.customer_address == "Carrera 9 no 7 17"
    assert services.session.customer_neighborhood == "Floridablanca casco antiguo"
    assert services.session.observations is not None
    assert "diagonal al banco dé Bogotá veterinaria Alma-vet" in services.session.observations
    assert "El pedido para las 12 dé dia" in services.session.observations


@pytest.mark.asyncio
async def test_labeled_address_extracts_embedded_barrio_and_payment_prefix_is_not_name() -> None:
    services = FakeConversationServices()
    services.session.add_cart_item(cart_item_from_product(services.products["BROASTER_CUARTO"], 1))
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(
        ConversationGraphState(
            chat_id=123,
            raw_text=(
                "Dirección: Calle 39 #5-125, barrio Lagos 2\n\n"
                "Que esté acá a la 1:00pm, por favor, antes no\n\n"
                "Pago en efectivo"
            ),
        )
    )

    assert result["current_step"] == ConversationState.ASK_CUSTOMER_DATA
    assert "nombre completo" in result["response_text"].lower()
    assert "telefono" in result["response_text"].lower()
    assert "barrio" not in result["response_text"].lower()
    assert services.session.customer_address == "Calle 39 #5-125"
    assert services.session.customer_neighborhood == "Lagos 2"
    assert services.session.payment_method == "Efectivo"
    assert services.session.customer_name is None
    assert "Que esté acá a la 1:00pm, por favor, antes no" in (services.session.observations or "")


@pytest.mark.asyncio
async def test_customer_data_accepts_optional_note_before_payment_method() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    state = ConversationGraphState(
        chat_id=123,
        raw_text=(
            "Angel David Pinzón\n"
            "3153327502\n"
            "Transversal 23 #52a-21\n"
            "san antonio del carrizal\n"
            "quiero que venga con extra de tartara porfa\n"
            "nequi"
        ),
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

    result = await build_conversation_graph(services).ainvoke(state)

    assert result["current_step"] == ConversationState.CHECKOUT_REVIEW
    assert "Datos recibidos" in result["response_text"]
    assert "Angel David Pinzón" in result["response_text"]
    assert "Transversal 23 #52a-21" in result["response_text"]
    assert "san antonio del carrizal" in result["response_text"]
    assert "extra de tartara" in result["response_text"]
    assert "Pago: Nequi" in result["response_text"]
    assert "El domicilio para" not in result["response_text"]
    assert services.session.observations == "quiero que venga con extra de tartara porfa"


@pytest.mark.asyncio
async def test_zero_from_customer_data_returns_to_cart() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    product = services.products["ASADO_ENTERO"]
    services.session.add_cart_item(cart_item_from_product(product, 2))
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="0")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "Tu orden" in result["response_text"]
    assert "Me falta esta informacion" not in result["response_text"]
    assert len(services.session.cart) == 1


@pytest.mark.asyncio
async def test_complete_customer_data_replaces_bad_cached_checkout_fields() -> None:
    services = FakeConversationServices()
    product = services.products["BROASTER_CUARTO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    services.session.customer_name = "0"
    services.session.customer_neighborhood = "0"
    services.session.observations = (
        "Muy buenos días me puedes colaborar con 2 pollos asados con tartar y ají, que valen?. "
        "Salsas asado solicitadas: ají."
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text=(
            "Wendy\n"
            "3022873946\n"
            "Transversal 29 # 145-84\n"
            "El Bosque\n"
            "Con tártara y ají\n"
            "Efectivo"
        ),
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.CHECKOUT_REVIEW
    assert "Cliente: Wendy" in result["response_text"]
    assert "Barrio: El Bosque" in result["response_text"]
    assert "Nota: Con tártara y ají" in result["response_text"]
    assert "Cliente: 0" not in result["response_text"]
    assert "Barrio: 0" not in result["response_text"]
    assert "Muy buenos días me puedes colaborar" not in result["response_text"]
    assert services.session.customer_name == "Wendy"
    assert services.session.customer_neighborhood == "El Bosque"
    assert services.session.observations == "Con tártara y ají"


@pytest.mark.asyncio
async def test_customer_data_accepts_optional_note_when_user_retries_checkout_data() -> None:
    services = FakeConversationServices()
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)
    state = ConversationGraphState(
        chat_id=123,
        raw_text=(
            "Ángel David Pinzón\n"
            "3153327502\n"
            "Transversal 23 #52a-21\n"
            "san antonio del carrizal\n"
            "el domicilio lo recoge mi hijo\n"
            "nequi"
        ),
    )

    result = await build_conversation_graph(services).ainvoke(state)

    assert result["current_step"] == ConversationState.CHECKOUT_REVIEW
    assert "san antonio del carrizal" in result["response_text"]
    assert "el domicilio lo recoge mi hijo" in result["response_text"]
    assert "Pago: Nequi" in result["response_text"]
    assert "El domicilio para" not in result["response_text"]
    assert services.session.observations == "el domicilio lo recoge mi hijo"


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
async def test_customer_data_ignores_filler_messages_and_does_not_confirm_with_bad_cached_fields() -> None:
    services = FakeConversationServices()
    product = services.products["BROASTER_CUARTO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    services.session.move_to(ConversationState.ASK_CUSTOMER_DATA)

    filler_state = ConversationGraphState(chat_id=123, raw_text="bueno, no importa")
    filler_state = await nodes.load_or_create_session(filler_state, services)
    filler_state = await nodes.extract_customer_data(filler_state, services)
    filler_state = await nodes.validate_customer_data(filler_state, services)

    assert filler_state.errors == [
        "nombre completo",
        "telefono",
        "direccion",
        "barrio",
        "metodo de pago",
    ]
    assert services.session.customer_name is None

    greeting_state = ConversationGraphState(chat_id=123, raw_text="holaaaaaaa")
    greeting_state = await nodes.load_or_create_session(greeting_state, services)
    greeting_state = await nodes.extract_customer_data(greeting_state, services)
    greeting_state = await nodes.validate_customer_data(greeting_state, services)

    assert greeting_state.errors == [
        "nombre completo",
        "telefono",
        "direccion",
        "barrio",
        "metodo de pago",
    ]
    assert services.session.customer_neighborhood is None

    partial_state = ConversationGraphState(
        chat_id=123,
        raw_text="3153327502\nTransversal 23 #52a-21\nsan antonio del carrizal\nnequi",
    )
    partial_state = await nodes.load_or_create_session(partial_state, services)
    partial_state = await nodes.extract_customer_data(partial_state, services)
    partial_state = await nodes.validate_customer_data(partial_state, services)

    assert partial_state.errors == ["nombre completo"]
    assert partial_state.current_step == ConversationState.ASK_CUSTOMER_DATA
    assert partial_state.customer.name is None
    assert partial_state.customer.phone == "3153327502"
    assert partial_state.customer.address == "Transversal 23 #52a-21"
    assert partial_state.customer.neighborhood == "san antonio del carrizal"
    assert partial_state.customer.observations is None
    assert partial_state.customer.payment_method == "Nequi"
    assert "Datos recibidos" not in partial_state.response_text


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
async def test_natural_pickup_order_accepts_name_and_phone_next_message() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    graph = build_conversation_graph(services)

    first = await graph.ainvoke(
        ConversationGraphState(chat_id=123, raw_text="Me regalas un asado para recoger")
    )

    assert first["current_step"] == ConversationState.POST_ADD
    assert first["fulfillment_type"] == "PICKUP"
    checkout_prompt = first["response_text"].split("Para confirmar tu orden", 1)[1]
    assert "Nombre completo" in checkout_prompt
    assert "Telefono" in checkout_prompt
    assert "Direccion" not in checkout_prompt
    assert services.session.fulfillment_type == "PICKUP"

    second = await graph.ainvoke(
        ConversationGraphState(chat_id=123, raw_text="Wendy\n3022873846")
    )

    assert second["current_step"] == ConversationState.CHECKOUT_REVIEW
    assert second["fulfillment_type"] == "PICKUP"
    assert "Datos recibidos" in second["response_text"]
    assert "orden para recoger" in second["response_text"]
    assert "Puedes escribirme tu orden en texto normal" not in second["response_text"]
    assert services.session.customer_name == "Wendy"
    assert services.session.customer_phone == "3022873846"


@pytest.mark.asyncio
async def test_pickup_mixed_asado_and_broaster_with_inline_name_and_time() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Buenas tardes"))
    result = await graph.ainvoke(
        ConversationGraphState(
            chat_id=123,
            raw_text=(
                "Buenas veci\n"
                "Para pedir medio pollo asado y 1/4 de pollo broaster pechuga, "
                "para rercoger a nombre de Santiago a la 1 pm"
            ),
        )
    )

    assert result["current_step"] == ConversationState.ASK_CUSTOMER_DATA
    assert result["fulfillment_type"] == "PICKUP"
    assert "1 x 1/2 Asado: $22300" in result["response_text"]
    assert "1 x 1/4 Broasted - Pechuga: $13500" in result["response_text"]
    assert "1/2 Broasted" not in result["response_text"]
    assert "Me falta esta informacion: telefono" in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == [
        "ASADO_MEDIO",
        "BROASTER_CUARTO",
    ]
    assert services.session.customer_name == "Santiago"
    assert services.session.customer_phone is None
    assert services.session.fulfillment_type == "PICKUP"
    assert services.session.observations == "Recoger a la 1 pm"


@pytest.mark.asyncio
async def test_transfer_customer_data_for_el_olympo_calculates_delivery_total() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Hola buen dia"))
    first = await graph.ainvoke(
        ConversationGraphState(chat_id=123, raw_text="Por favor para pedir medio pollo broster")
    )

    assert "1 x 1/2 Broasted: $25500" in first["response_text"]

    data = await graph.ainvoke(
        ConversationGraphState(
            chat_id=123,
            raw_text=(
                "Naggibe Pinilla\n"
                "3004067345\n"
                "Conjunto el Olympo por al 200 torre 5 apartamento 1302\n"
                "Transferencia"
            ),
        )
    )

    assert data["current_step"] == ConversationState.CHECKOUT_REVIEW
    assert "La cuenta de Nequi" not in data["response_text"]
    assert "Domicilio: $7000" in data["response_text"]
    assert "Total: $32500" in data["response_text"]
    assert "¿Confirmas tu orden?" in data["response_text"]
    assert services.session.customer_name == "Naggibe Pinilla"
    assert services.session.customer_phone == "3004067345"
    assert services.session.customer_neighborhood == "el Olympo"
    assert services.session.payment_method == "Transferencia Bancolombia"

    total = await graph.ainvoke(
        ConversationGraphState(chat_id=123, raw_text="Me confirma el total incluido domicilio")
    )

    assert total["current_step"] == ConversationState.CHECKOUT_REVIEW
    assert "Domicilio: $7000" in total["response_text"]
    assert "Total: $32500" in total["response_text"]
    assert "Total: $25500" not in total["response_text"]


@pytest.mark.asyncio
async def test_broaster_quarters_with_customer_data_and_bellavista_delivery_checkout() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Hola"))
    result = await graph.ainvoke(
        ConversationGraphState(
            chat_id=123,
            raw_text=(
                "Por favor me envia\n\n"
                "3 cuartos de pollo a la broster (2pierna pernil\n"
                "1 pechuga)\n\n"
                "Sandra Milena Rodriguez\n\n"
                "3202957129\n\n"
                "Altos de Bellavista sector 17 bloque 3-8 apto 304\n\n"
                "Efectivo"
            ),
        )
    )

    assert result["current_step"] == ConversationState.CHECKOUT_REVIEW
    assert "Si, recibimos Efectivo" not in result["response_text"]
    assert "2 x 1/4 Broasted - Pierna: $27000" in result["response_text"]
    assert "1 x 1/4 Broasted - Pechuga: $13500" in result["response_text"]
    assert "Cliente: Sandra Milena Rodriguez" in result["response_text"]
    assert "Domicilio: $4000" in result["response_text"]
    assert "Total: $44500" in result["response_text"]
    assert [item.product_name.value for item in services.session.cart] == [
        "1/4 Broasted - Pierna",
        "1/4 Broasted - Pechuga",
    ]
    assert [item.quantity for item in services.session.cart] == [2, 1]
    assert services.session.customer_name == "Sandra Milena Rodriguez"
    assert services.session.customer_phone == "3202957129"
    assert services.session.customer_address == "Altos de Bellavista sector 17 bloque 3-8 apto 304"
    assert services.session.customer_neighborhood == "Altos de Bellavista"
    assert services.session.payment_method == "Efectivo"

    drinks = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="bebidas"))

    assert drinks["current_step"] == ConversationState.SELECT_BEBIDA
    assert "🥤 Bebidas" in drinks["response_text"]
    assert len(services.session.cart) == 2

    no_drink = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="No sin bebida"))

    assert no_drink["current_step"] == ConversationState.CHECKOUT_REVIEW
    assert "🥤 Bebidas" not in no_drink["response_text"]
    assert "Domicilio: $4000" in no_drink["response_text"]
    assert "Total: $44500" in no_drink["response_text"]
    assert "Pago: Efectivo" in no_drink["response_text"]
    assert [item.product_name.value for item in services.session.cart] == [
        "1/4 Broasted - Pierna",
        "1/4 Broasted - Pechuga",
    ]
    assert [item.quantity for item in services.session.cart] == [2, 1]

    confirmation = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Si solo esto"))

    assert confirmation["current_step"] == ConversationState.MAIN_MENU
    assert "Orden confirmada" in confirmation["response_text"]
    assert "La cuenta de Nequi" not in confirmation["response_text"]
    assert len(services.synced_orders) == 1
    assert services.synced_orders[0].payment_method == "Efectivo"
    assert [(item.product_name, item.quantity) for item in services.synced_orders[0].items] == [
        ("1/4 Broasted - Pierna", 2),
        ("1/4 Broasted - Pechuga", 1),
    ]
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_graph_adds_whole_broster_order_like_whole_asado() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Muy buenas tardes veci me vendes 2 pollos broster con adicional de miel porfavor",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "2 x Broasted Entero" in result["response_text"]
    assert "1 x Adicional de Salsas - Miel" in result["response_text"]
    assert "Total acumulado: $102900" in result["response_text"]
    assert len(services.session.cart) == 2
    assert services.session.cart[0].product_code == ProductCode("BROASTER_ENTERO")
    assert services.session.cart[0].quantity == 2
    assert services.session.cart[1].product_code == ProductCode("ADICIONAL_SALSAS")
    assert services.session.cart[1].product_name == ProductName("Adicional de Salsas - Miel")
    assert services.session.cart[1].quantity == 1
    assert services.session.observations is None


@pytest.mark.asyncio
async def test_natural_order_with_address_keeps_customer_fields_and_no_whole_chicken_part() -> None:
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
        raw_text=(
            "Me puedes enviar un pollo asado\n\n"
            "para la calle 195 No. 28-15 barrio villa piedra del sol"
        ),
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "- 1 x 1 Asado Entero: $44500" in result["response_text"]
    assert "1 Asado Entero - Pierna" not in result["response_text"]
    assert "Direccion" not in result["response_text"]
    assert "Barrio" not in result["response_text"]
    assert "nombre completo" in result["response_text"]
    assert "telefono" in result["response_text"]
    assert "metodo de pago" in result["response_text"]
    assert services.session.customer_address == "calle 195 No. 28-15"
    assert services.session.customer_neighborhood == "villa piedra del sol"


@pytest.mark.asyncio
async def test_graph_tolerates_broche_autocorrect_for_quarter_broaster() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Porfa para pedir un cuarto broche pechuga ala a la calle 5 número número 40-37 lagos 2 -",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x 1/4 Broasted - Pechuga" in result["response_text"]
    assert "Puedes escribirme tu orden" not in result["response_text"]
    assert len(services.session.cart) == 1
    assert services.session.cart[0].product_code == ProductCode("BROASTER_CUARTO")
    assert services.session.cart[0].product_name == ProductName("1/4 Broasted - Pechuga")


@pytest.mark.asyncio
async def test_graph_tolerates_common_broaster_typo_for_whole_chicken() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="me vende dos pollos bruster"))

    assert result["current_step"] == ConversationState.POST_ADD
    assert "2 x Broasted Entero" in result["response_text"]
    assert services.session.cart[0].product_code == ProductCode("BROASTER_ENTERO")
    assert services.session.cart[0].quantity == 2


@pytest.mark.asyncio
async def test_graph_adds_mixed_whole_brosters_and_asado_in_one_message() -> None:
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
        raw_text="Buenos días me vendes dos pollos brosters y un pollo asado",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "2 x Broasted Entero" in result["response_text"]
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert "Total acumulado: $146500" in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == [
        "ASADO_ENTERO",
        "BROASTER_ENTERO",
    ]
    assert [item.quantity for item in services.session.cart] == [1, 2]


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
async def test_natural_order_with_coca_cola_without_size_asks_drink_type() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Un pollo asado con yuca y una Coca-Cola")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert "Papa Francesa" not in result["response_text"]
    assert "tambien quieres una gaseosa" in result["response_text"]
    assert "Coca-Cola 1.5 L" in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == ["ASADO_ENTERO"]


@pytest.mark.asyncio
async def test_ambiguous_coca_cola_alone_asks_size_with_prices_without_fallback() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="dame una coca cola")

    result = await graph.ainvoke(state)

    assert "Coca-Cola personal 400 ml - $3500" in result["response_text"]
    assert "Coca-Cola 1.5 L - $8500" in result["response_text"]
    assert "Por ahora no cuento con informacion" not in result["response_text"]
    assert "Puedes escribirme tu orden" not in result["response_text"]
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_coca_cola_clarification_then_personal_adds_drink_to_existing_order() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    services.session.add_cart_item(cart_item_from_product(services.products["ASADO_ENTERO"], 1))
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)

    question = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="con una coca cola"))
    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="personal"))

    assert "Coca-Cola personal 400 ml - $3500" in question["response_text"]
    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x Coca-Cola personal 400 ml" in result["response_text"]
    assert "vale $3500" not in result["response_text"]
    assert "Puedes escribirme tu orden" not in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == ["ASADO_ENTERO", "PERSONAL_400"]


@pytest.mark.asyncio
async def test_coca_cola_clarification_then_number_adds_litro_y_medio() -> None:
    services = FakeConversationServices()
    services.products["COCA_COLA_15"] = Product(
        code=ProductCode("COCA_COLA_15"),
        name=ProductName("Coca-Cola 1.5 L"),
        category=ProductCategory.BEBIDAS,
        price=MoneyCOP(8500),
    )
    graph = build_conversation_graph(services)

    await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="dame una coca cola"))
    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="2"))

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x Coca-Cola 1.5 L" in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == ["COCA_COLA_15"]


@pytest.mark.asyncio
async def test_ambiguous_water_alone_asks_variant_with_price_without_adding_default() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="quiero un agua")

    result = await graph.ainvoke(state)

    assert "agua botella por $2600" in result["response_text"]
    assert "Con gas" in result["response_text"]
    assert "Sin gas" in result["response_text"]
    assert "Saborizada" in result["response_text"]
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_water_clarification_then_variant_continues_product_flow() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="quiero un agua"))
    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="sin gas"))

    assert result["current_step"] == ConversationState.ASK_QUANTITY
    assert "Agua botella - Sin gas" in result["response_text"]
    assert "¿Cuantas unidades deseas añadir?" in result["response_text"]


@pytest.mark.asyncio
async def test_ambiguous_gaseosa_alone_lists_drinks_with_prices() -> None:
    services = FakeConversationServices()
    services.products["COCA_COLA_15"] = Product(
        code=ProductCode("COCA_COLA_15"),
        name=ProductName("Coca-Cola 1.5 L"),
        category=ProductCategory.BEBIDAS,
        price=MoneyCOP(8500),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="dame una gaseosa")

    result = await graph.ainvoke(state)

    assert "🥤 Bebidas" in result["response_text"]
    assert "Coca-Cola personal 400 ml - $3500" in result["response_text"]
    assert "Coca-Cola 1.5 L - $8500" in result["response_text"]
    assert "Gaseosa 2.5 L - $8500" in result["response_text"]
    assert services.session.cart == []


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
async def test_natural_order_with_manzana_litro_warns_only_25_liter_available() -> None:
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
        raw_text="Buena tarde me puede enviar por favor un pollo asado y una manzana litro",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert "gaseosa Manzana solo la manejamos en presentacion 2.5 L" in result["response_text"]
    assert "Precio: $8500" in result["response_text"]
    assert "Gaseosa 2.5 L - Manzana" not in result["response_text"]
    assert [item.product_code for item in services.session.cart] == [ProductCode("ASADO_ENTERO")]


@pytest.mark.asyncio
async def test_manzana_litro_alone_warns_only_25_liter_available() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="manzana litro y medio"))

    assert "gaseosa Manzana solo la manejamos en presentacion 2.5 L" in result["response_text"]
    assert "Precio: $8500" in result["response_text"]
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_natural_order_with_manzana_25_adds_soda_variant() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="quiero una manzana 2.5"))

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x Gaseosa 2.5 L - Manzana" in result["response_text"]
    assert services.session.cart[0].product_code == ProductCode("GASEOSA_25")
    assert services.session.cart[0].product_name == ProductName("Gaseosa 2.5 L - Manzana")


@pytest.mark.asyncio
async def test_natural_order_with_unavailable_lasagna_explains_not_added(monkeypatch) -> None:
    monkeypatch.setattr(nodes, "_business_today", lambda: date(2026, 7, 1))
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

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert "1 x Gaseosa 2.5 L - Kola" in result["response_text"]
    assert "Lasagna Mixta solo esta disponible fines de semana" in result["response_text"]
    assert "Selecciona menu" in result["response_text"]
    assert all(item.product_code.value != "LASAGNA_MIXTA" for item in services.session.cart)
    assert len(services.session.cart) == 2


@pytest.mark.asyncio
async def test_whatsapp_bulleted_delivery_order_adds_available_items_and_asks_missing_identity(
    monkeypatch,
) -> None:
    monkeypatch.setattr(nodes, "_business_today", lambda: date(2026, 7, 20))
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    graph = build_conversation_graph(services)
    message = (
        "Buenos dias. Dame por favor lo siguiente:\n"
        "- 1 lasaña\n"
        "- ⁠1 cuarto de pollo broaster pierna pernil\n"
        "- ⁠1 cuarto de pollo asado pierna pernil\n"
        "- ⁠1 pollo asado completo\n\n"
        "Direccion: Calle 39 #5-125, barrio Lagos 2\n"
        "Pago en efectivo, cuanto es el total?\n\n"
        "*Que este aca a las 12:30pm, por favor, antes no*"
    )

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text=message))

    assert result["current_step"] == ConversationState.ASK_CUSTOMER_DATA
    assert "Tu orden esta vacia" not in result["response_text"]
    assert "Puedes escribirme tu orden en texto normal" not in result["response_text"]
    assert "1 x 1/4 Broasted - Pierna: $13500" in result["response_text"]
    assert "1 x 1/4 Asado - Pierna: $11800" in result["response_text"]
    assert "1 x 1 Asado Entero: $44500" in result["response_text"]
    assert "Lasagna Mixta solo esta disponible fines de semana" in result["response_text"]
    assert "Total con domicilio: $71800" in result["response_text"]
    assert "Me falta esta informacion: nombre completo, telefono" in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == [
        "ASADO_CUARTO",
        "ASADO_ENTERO",
        "BROASTER_CUARTO",
    ]
    assert services.session.customer_address == "Calle 39 #5-125, barrio"
    assert services.session.customer_neighborhood == "Lagos 2"
    assert services.session.payment_method == "Efectivo"
    assert services.session.observations == "*Que este aca a las 12:30pm. antes no*"


@pytest.mark.asyncio
async def test_lasagna_availability_question_shows_unavailable_alternative(monkeypatch) -> None:
    monkeypatch.setattr(nodes, "_business_today", lambda: date(2026, 7, 1))
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Hay lasañas?")

    result = await graph.ainvoke(state)

    assert "Lasagna Mixta solo esta disponible fines de semana" in result["response_text"]
    assert "Selecciona menu" in result["response_text"]


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

    assert result["current_step"] == ConversationState.ASK_CHICKEN_STYLE
    assert "¿Lo quieres asado o broster?" in result["response_text"]
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
async def test_soup_availability_question_does_not_show_addons_or_add_soup() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Una pregunta hay sopas?")

    result = await graph.ainvoke(state)

    assert "incluye sopa" in result["response_text"].lower()
    assert "🍟 Adicionales" not in result["response_text"]
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_post_add_soup_question_uses_last_chicken_product_without_adding_soup() -> None:
    services = FakeConversationServices()
    product = services.products["BROASTER_ENTERO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Viene con sopa?")

    result = await graph.ainvoke(state)

    assert "incluye 2 sopas sin costo" in result["response_text"].lower()
    assert "papa francesa" in result["response_text"].lower()
    assert "tartara" in result["response_text"].lower()
    assert "miel" in result["response_text"].lower()
    assert "salsa de tomate" in result["response_text"].lower()
    assert "yuca cocida" not in result["response_text"].lower()
    assert "ají" not in result["response_text"].lower()
    assert "Sopa Adicional" not in result["response_text"]
    assert len(services.session.cart) == 1
    assert services.session.cart[0].product_code == ProductCode("BROASTER_ENTERO")


@pytest.mark.asyncio
async def test_chicken_soup_question_does_not_add_soup_to_cart() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="El pollo viene con sopa?")

    result = await graph.ainvoke(state)

    assert "incluye sopa" in result["response_text"].lower()
    assert "trae pollo asado" not in result["response_text"].lower()
    assert "Sopa Adicional" not in result["response_text"]
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_order_with_soup_question_adds_chicken_only_and_answers_contents() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Me regalas un pollo asado, con que viene? Trae sopa?")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x 1 Asado Entero: $44500" in result["response_text"]
    assert "Sopa Adicional" not in result["response_text"]
    assert "papa" in result["response_text"].lower()
    assert "yuca cocida" in result["response_text"].lower()
    assert "ají" in result["response_text"]
    assert "incluye 2 sopas sin costo" in result["response_text"].lower()
    assert len(services.session.cart) == 1
    assert services.session.cart[0].product_code == ProductCode("ASADO_ENTERO")


@pytest.mark.asyncio
async def test_real_customer_half_asado_soup_request_keeps_single_chicken_and_collects_split_data() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    assert (await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Buenas")))["current_step"] == ConversationState.MAIN_MENU
    assert (await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Tardes")))["current_step"] == ConversationState.MAIN_MENU
    style = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Medio pollo"))

    assert style["current_step"] == ConversationState.ASK_CHICKEN_STYLE

    added = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Asado"))

    assert added["current_step"] == ConversationState.POST_ADD
    assert "1 x 1/2 Asado: $22300" in added["response_text"]

    price = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Que vale"))

    assert price["current_step"] == ConversationState.POST_ADD
    assert "1/2 Asado vale $22300" in price["response_text"]

    soup = await graph.ainvoke(
        ConversationGraphState(
            chat_id=123,
            raw_text="Medio pollo asada que bien asado y me dan sopa porfavor y agi",
        )
    )

    assert soup["current_step"] == ConversationState.POST_ADD
    assert "Sopa Adicional" not in soup["response_text"]
    assert "Añadido a tu orden" not in soup["response_text"]
    assert "incluye 1 sopa sin costo" in soup["response_text"].lower()
    assert [item.product_code.value for item in services.session.cart] == ["ASADO_MEDIO"]
    assert services.session.cart[0].quantity == 1

    for raw_text in ("Blanca", "3175776691", "Lagos 2", "Calle 40 #6-18"):
        result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text=raw_text))
        assert result["current_step"] == ConversationState.ASK_CUSTOMER_DATA

    review = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Efectivo"))

    assert review["current_step"] == ConversationState.CHECKOUT_REVIEW
    assert "Subtotal: $22300" in review["response_text"]
    assert "Domicilio: $2000" in review["response_text"]
    assert "Total: $24300" in review["response_text"]
    assert services.session.customer_name == "Blanca"
    assert services.session.customer_phone == "3175776691"
    assert services.session.customer_neighborhood == "Lagos 2"
    assert services.session.customer_address == "Calle 40 #6-18"
    assert services.session.payment_method == "Efectivo"

    total = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Gracias cuanto es"))

    assert total["current_step"] == ConversationState.CHECKOUT_REVIEW
    assert "Total: $24300" in total["response_text"]

    confirmation = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Si"))

    assert confirmation["current_step"] == ConversationState.MAIN_MENU
    assert "Orden confirmada" in confirmation["response_text"]
    assert len(services.synced_orders) == 1
    assert [(item.product_code, item.quantity) for item in services.synced_orders[0].items] == [
        ("ASADO_MEDIO", 1),
    ]


@pytest.mark.asyncio
async def test_contents_question_after_cart_uses_last_chicken_product() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    product = services.products["ASADO_ENTERO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Con que viene?"))

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 Asado Entero vale $44500" in result["response_text"]
    assert "papa" in result["response_text"].lower()
    assert "yuca cocida" in result["response_text"].lower()
    assert "ají" in result["response_text"]
    assert "incluye 2 sopas sin costo" in result["response_text"].lower()
    assert "Dime de que producto" not in result["response_text"]
    assert len(services.session.cart) == 1


@pytest.mark.asyncio
async def test_contents_question_for_asado_defaults_to_whole_roasted_chicken() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Que trae el asado"))

    assert "1 Asado Entero vale $44500" in result["response_text"]
    assert "papa" in result["response_text"].lower()
    assert "yuca cocida" in result["response_text"].lower()
    assert "ají" in result["response_text"]
    assert "incluye 2 sopas sin costo" in result["response_text"].lower()
    assert "Dime de que producto" not in result["response_text"]
    assert services.session.cart == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_text", "expected"),
    [
        ("Cuántas presas trae un pollo entero?", "trae 8 presas"),
        ("Cuantas piezas trae medio pollo broster?", "trae 4 presas"),
        ("Cuantas porciones trae 3/4 de pollo asado?", "trae 6 presas"),
        ("Cuantos trozos trae un cuarto broaster?", "trae 2 presas"),
        ("Cuantas partes trae el pollo asado?", "trae 8 presas"),
    ],
)
async def test_chicken_piece_count_questions_answer_by_presentation(raw_text: str, expected: str) -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text=raw_text))

    assert expected in result["response_text"]
    assert "2 pechugas, 2 alas, 2 perniles y 2 muslos" in result["response_text"]
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_sauce_change_question_is_answered_and_saved_as_note() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    product = services.products["ASADO_ENTERO"]
    services.session.add_cart_item(cart_item_from_product(product, 2))
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Y le puedo adicionar tártara en vez de ají?")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "Si claro" in result["response_text"]
    assert "tártara en vez de ají" in result["response_text"]
    assert "Ya lo dejo anotado" in result["response_text"]
    assert "Salsas solicitadas: tártara en vez de ají." in (services.session.observations or "")
    assert len(services.session.cart) == 1


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
    assert "¿Quieres seguir con tu orden o prefieres cancelarla?" in result["response_text"]
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

    assert "seguimos con tu orden sin sopa" in result["response_text"].lower()
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

    assert "Broasted Entero vale $51000" in result["response_text"]
    assert "papa francesa" in result["response_text"].lower()
    assert "tartara" in result["response_text"].lower()
    assert "miel" in result["response_text"].lower()
    assert "salsa de tomate" in result["response_text"].lower()
    assert "yuca cocida" not in result["response_text"].lower()
    assert "ají" not in result["response_text"]
    assert "Añadido al carrito" not in result["response_text"]
    assert services.session.cart == []


@pytest.mark.asyncio
async def test_combination_question_does_not_add_half_broaster_to_cart() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Puedo pedir medio asado y medio a la broster?")

    result = await graph.ainvoke(state)

    assert "puedes ordenar medio asado y medio broaster" in result["response_text"].lower()
    assert "Añadido al carrito" not in result["response_text"]
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
async def test_real_customer_half_asado_half_broaster_order_with_address_and_sauces() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Buenas"))
    added = await graph.ainvoke(
        ConversationGraphState(
            chat_id=123,
            raw_text="Me das un pollo entero medio asado y medio a la broster porfa",
        )
    )

    assert added["current_step"] == ConversationState.POST_ADD
    assert "¿Lo quieres asado o broster?" not in added["response_text"]
    assert "1 x 1/2 Asado: $22300" in added["response_text"]
    assert "1 x 1/2 Broasted: $25500" in added["response_text"]
    assert [item.product_code.value for item in services.session.cart] == [
        "ASADO_MEDIO",
        "BROASTER_MEDIO",
    ]

    address = await graph.ainvoke(
        ConversationGraphState(
            chat_id=123,
            raw_text="Con tártara y aji para la calle 47 #4 - 65 lagos 2",
        )
    )

    assert address["current_step"] == ConversationState.ASK_CUSTOMER_DATA
    assert "Me falta esta informacion: nombre completo, telefono, metodo de pago" in address["response_text"]
    assert services.session.customer_address == "calle 47 #4 - 65"
    assert services.session.customer_neighborhood == "lagos 2"
    assert services.session.observations == "Salsas solicitadas: ají, tártara."

    total_question = await graph.ainvoke(
        ConversationGraphState(chat_id=123, raw_text="Cuanto se demora? Y cuanto es?")
    )

    assert total_question["current_step"] == ConversationState.ASK_CUSTOMER_DATA
    assert services.session.customer_name is None
    assert services.session.customer_address == "calle 47 #4 - 65"
    assert services.session.customer_neighborhood == "lagos 2"


@pytest.mark.asyncio
async def test_real_customer_half_broaster_with_address_and_transfer_does_not_fallback() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    greeting = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="¡Hola, linda tarde!"))

    assert greeting["current_step"] == ConversationState.MAIN_MENU
    assert "Puedes escribirme tu orden en texto normal" not in greeting["response_text"]

    result = await graph.ainvoke(
        ConversationGraphState(
            chat_id=123,
            raw_text=(
                "Quisiera ordenar\n"
                "1/2 pollo a la broáster ¡Por favor!\n"
                "Para Calle 46 #4-41 Lagos 2.\n"
                "Para pagar por transferencia ¡Porfa!"
            ),
        )
    )

    assert result["current_step"] == ConversationState.ASK_CUSTOMER_DATA
    assert "La cuenta de Nequi" not in result["response_text"]
    assert "Puedes escribirme tu orden en texto normal" not in result["response_text"]
    assert "1 x 1/2 Broasted: $25500" in result["response_text"]
    assert "Domicilio: $2000" in result["response_text"]
    assert "Total con domicilio: $27500" in result["response_text"]
    assert "Me falta esta informacion: nombre completo, telefono" in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == ["BROASTER_MEDIO"]
    assert services.session.customer_name is None
    assert services.session.customer_phone is None
    assert services.session.customer_address == "Calle 46 #4-41"
    assert services.session.customer_neighborhood == "Lagos 2"
    assert services.session.payment_method == "Transferencia Bancolombia"


@pytest.mark.asyncio
async def test_half_combo_menu_button_shows_menu_without_adding_cart() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.ASK_HALF_COMBO)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="ver menu")

    result = await graph.ainvoke(state)

    assert "Bienvenid@ a Mac Chicken" in result["response_text"]
    assert result["current_step"] == ConversationState.MAIN_MENU
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
@pytest.mark.parametrize(
    "raw_text",
    [
        "Para un domicilio",
        "Para un domicilio, por favor",
        "Tienen disponibilidad?",
        "Están atendiendo?",
        "Hay servicio a domicilio?",
    ],
)
async def test_generic_service_or_delivery_question_answers_yes_with_menu(raw_text: str) -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text=raw_text)

    result = await graph.ainvoke(state)

    assert "estamos atendiendo" in result["response_text"].lower()
    assert "servicio a domicilio" in result["response_text"].lower()
    assert "seleccionar menu" in result["response_text"]
    assert "cuesta $" not in result["response_text"]
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
@pytest.mark.parametrize(
    "raw_text",
    [
        "¿¿ demora ??",
        "Se demora??",
        "cuánto   demora???",
        "En cuánto tiempo, me despachan?",
        "Ya salió?",
        "viene en camino?",
        "cuando llega",
        "Mi pedido llegó ?",
        "Si llevaron el domicilio ?",
        "Lo pedí hace una hora exactamente",
        "Una hora y 3 minutos y no lo han enviado o ya se envió ?",
        "Es que estamos a 4 cuadras y llevo una hora esperando que salga",
    ],
)
async def test_punctuation_accents_and_spacing_do_not_break_delay_questions(raw_text: str) -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text=raw_text)

    result = await graph.ainvoke(state)

    assert "40 minutos" in result["response_text"]
    assert "Puedes escribirme tu orden" not in result["response_text"]


@pytest.mark.asyncio
async def test_order_status_question_breaks_out_of_free_order_fallback_loop() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.NATURAL_ORDER)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Mi pedido llegó ?")

    result = await graph.ainvoke(state)

    assert "40 minutos" in result["response_text"]
    assert "Puedes escribirme tu orden" not in result["response_text"]


@pytest.mark.asyncio
async def test_refund_followup_breaks_out_of_free_order_fallback_loop() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.NATURAL_ORDER)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Me regresan a mi cuenta ?")

    result = await graph.ainvoke(state)

    assert "devoluciones" in result["response_text"].lower()
    assert "Puedes escribirme tu orden" not in result["response_text"]


@pytest.mark.asyncio
async def test_short_delay_question_gets_friendly_answer_without_fallback_loop() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="demora?")

    result = await graph.ainvoke(state)

    assert "40 minutos" in result["response_text"]
    assert "Puedes escribirme tu orden" not in result["response_text"]
    assert len(services.session.cart) == 0


@pytest.mark.asyncio
async def test_complaint_with_profanity_does_not_enter_order_fallback() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="perro hijueputa me robaron el pollo")

    result = await graph.ainvoke(state)

    assert "administrador" in result["response_text"].lower()
    assert "Puedes escribirme tu orden" not in result["response_text"]
    assert "catalogo del asadero" not in result["response_text"]


@pytest.mark.asyncio
async def test_empty_order_complaint_does_not_enter_catalog_unknown() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="oye es que el pedido me llegó vacio")

    result = await graph.ainvoke(state)

    assert "administrador" in result["response_text"].lower()
    assert "catalogo del asadero" not in result["response_text"]
    assert "Puedes escribirme tu orden" not in result["response_text"]


@pytest.mark.asyncio
async def test_payment_account_question_answers_nequi_account_without_cancelling() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Si fuese a cancelar por transferencia, que cuenta sería?",
    )

    result = await graph.ainvoke(state)

    assert "3182705144" in result["response_text"]
    assert "Fabio Leonardo Perez" in result["response_text"]
    assert "Cancele la orden actual" not in result["response_text"]
    assert len(services.session.cart) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_text",
    [
        "¿Pago por Nequí?",
        "Transferéncia, qué cuenta sería???",
        "Si fuese a cancelar por transferencia, qué cuenta sería?",
    ],
)
async def test_punctuation_accents_and_spacing_do_not_break_payment_account_questions(raw_text: str) -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text=raw_text)

    result = await graph.ainvoke(state)

    assert "3182705144" in result["response_text"]
    assert "Fabio Leonardo Perez" in result["response_text"]
    assert "Cancele la orden actual" not in result["response_text"]


@pytest.mark.asyncio
async def test_gratitude_after_order_does_not_enter_natural_order_fallback() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Muchas gracias")

    result = await graph.ainvoke(state)

    assert "Bienvenid@ a Mac Chicken" in result["response_text"]
    assert "Puedes escribirme tu pedido" not in result["response_text"]
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
    assert "Claro, te ayudo con otra orden" in state.response_text
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

    assert "solo esta disponible fines de semana" in result.response_text.lower()
    assert "Selecciona menu" in result.response_text
    assert len(services.session.cart) == 0


@pytest.mark.asyncio
async def test_weekend_lasagna_marked_unavailable_answers_out_of_stock(monkeypatch) -> None:
    monkeypatch.setattr(nodes, "_business_today", lambda: date(2026, 7, 4))
    services = FakeConversationServices()
    services.products["LASAGNA_MIXTA"].is_available = False
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="hay lasaña?"))

    assert "En este momento no tenemos Lasagna Mixta disponible" in result["response_text"]
    assert "solo esta disponible fines de semana" not in result["response_text"]


@pytest.mark.asyncio
async def test_weekday_maduro_question_answers_calendar_restriction(monkeypatch) -> None:
    monkeypatch.setattr(nodes, "_business_today", lambda: date(2026, 7, 1))
    services = FakeConversationServices()
    graph = build_conversation_graph(services)

    result = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="hay maduro con queso?"))

    assert "Maduro con Queso solo esta disponible fines de semana" in result["response_text"]


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
    assert route_after_intent(second_state) == "show_main_menu"
    second_result = await nodes.show_main_menu(second_state, services)

    assert first_result.current_step == ConversationState.PRODUCT_CATEGORY
    assert second_result.current_step == ConversationState.MAIN_MENU
    assert "Bienvenid@ a Mac Chicken" in second_result.response_text


@pytest.mark.asyncio
async def test_addons_menu_hides_internal_soup_icopor() -> None:
    services = FakeConversationServices()
    services.products["ICOPOR"] = Product(
        code=ProductCode("ICOPOR"),
        name=ProductName("Icopores"),
        category=ProductCategory.ADICIONALES,
        price=MoneyCOP(900),
    )
    services.products["BOTELLA_VIDRIO"] = Product(
        code=ProductCode("BOTELLA_VIDRIO"),
        name=ProductName("Botella Vidrio"),
        category=ProductCategory.ADICIONALES,
        price=MoneyCOP(200),
    )
    state = ConversationGraphState(chat_id=123, raw_text="adicionales")

    result = await nodes.show_addons_menu(state, services)

    assert "Icopor Sopa" not in result.response_text
    assert "Icopores" not in result.response_text
    assert "Botella Vidrio" not in result.response_text
    assert "Adicional de Salsas" in result.response_text


@pytest.mark.asyncio
async def test_main_menu_greeting_after_completed_order_sends_welcome_menu() -> None:
    services = FakeConversationServices()
    services.session.move_to(ConversationState.MAIN_MENU)
    state = ConversationGraphState(chat_id=123, raw_text="gracias")

    state = await nodes.normalize_message(state, services)
    state = await nodes.load_or_create_session(state, services)
    state = await nodes.detect_intent(state, services)

    assert route_after_intent(state) == "show_main_menu"
    result = await nodes.show_main_menu(state, services)
    assert "Bienvenid@ a Mac Chicken" in result.response_text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected_route"),
    [
        ("quiero ver el menu principal", "show_main_menu"),
        ("hola buenas", "show_main_menu"),
        ("quiero pedir por menu", "show_main_menu"),
        ("quiero pedir escribiendo", "show_main_menu"),
        ("quiero ver carrito", "show_cart"),
        ("quiero ver horarios", "show_schedules"),
        ("quiero finalizar pedido", "ask_customer_data"),
        ("quiero terminar mi pedido", "ask_customer_data"),
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
async def test_cart_change_removes_named_product_and_adds_preferred_product() -> None:
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
    services.session.add_cart_item(cart_item_from_product(services.products["BROASTER_ENTERO"], 1))
    services.session.add_cart_item(cart_item_from_product(services.products["COCA_COLA_15"], 1))
    services.session.add_cart_item(cart_item_from_product(services.products["ASADO_ENTERO"], 1))
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="quita el pollo a la broaster, se me antojo mejor un pollo asado",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "quite Broasted Entero" in result["response_text"]
    assert "- 1 x 1 Asado Entero: $44500" in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == [
        "COCA_COLA_15",
        "ASADO_ENTERO",
        "ASADO_ENTERO",
    ]
    assert sum(item.subtotal.amount for item in services.session.cart) == 97500


@pytest.mark.asyncio
async def test_cart_change_understands_ya_no_quiero_sino_language() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    services.session.add_cart_item(cart_item_from_product(services.products["ASADO_ENTERO"], 1))
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="no veci ya no quiero asado sino un broaster entero")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "quite 1 Asado Entero" in result["response_text"]
    assert "1 x Broasted Entero" in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == ["BROASTER_ENTERO"]


@pytest.mark.asyncio
async def test_cart_change_understands_short_por_asado_replacement() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    services.session.add_cart_item(cart_item_from_product(services.products["BROASTER_ENTERO"], 1))
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="cambiame el broaster por asado")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "quite Broasted Entero" in result["response_text"]
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == ["ASADO_ENTERO"]


@pytest.mark.asyncio
async def test_cart_change_replaces_only_one_asado_when_customer_says_un_asado() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    services.session.add_cart_item(cart_item_from_product(services.products["ASADO_ENTERO"], 2))
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="quiero cambiar un asado por un broster")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert [item.product_code.value for item in services.session.cart] == ["ASADO_ENTERO", "BROASTER_ENTERO"]
    assert [item.quantity for item in services.session.cart] == [1, 1]
    assert "1 x Broasted Entero" in result["response_text"]


@pytest.mark.asyncio
async def test_cart_change_all_order_with_quarters_waits_for_distribution_then_adds_everything() -> None:
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
    services.session.add_cart_item(cart_item_from_product(services.products["BROASTER_ENTERO"], 1))
    services.session.add_cart_item(cart_item_from_product(services.products["ASADO_ENTERO"], 1))
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)

    first = await graph.ainvoke(
        ConversationGraphState(
            chat_id=123,
            raw_text="Me equivoqué lo quiero cambiar por 4 cuartos de pollo asado un pollo broster y 3 cocacola litro y medio",
        )
    )
    assert first["current_step"] == ConversationState.ASK_CHICKEN_PART
    assert "Me faltan definir 4 cuarto" in first["response_text"]
    assert services.session.cart == []

    second = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="pierna"))
    assert second["current_step"] == ConversationState.ASK_CHICKEN_PART
    assert "Cuantos cuarto(s) quieres en pierna" in second["response_text"]

    third = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="2"))
    assert third["current_step"] == ConversationState.ASK_CHICKEN_PART
    assert "Me faltan definir 2 cuarto" in third["response_text"]
    assert services.session.cart == []

    fourth = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="2 pechugas"))
    assert fourth["current_step"] == ConversationState.POST_ADD
    assert "2 x 1/4 Asado - Pierna" in fourth["response_text"]
    assert "2 x 1/4 Asado - Pechuga" in fourth["response_text"]
    assert "1 x Broasted Entero" in fourth["response_text"]
    assert "3 x Coca-Cola 1.5 L" in fourth["response_text"]
    assert [item.product_code.value for item in services.session.cart] == [
        "ASADO_CUARTO",
        "ASADO_CUARTO",
        "BROASTER_ENTERO",
        "COCA_COLA_15",
    ]


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
async def test_asado_with_default_papa_and_yuca_does_not_charge_french_fries() -> None:
    services = FakeConversationServices()
    services.products["ASADO_ENTERO"] = Product(
        code=ProductCode("ASADO_ENTERO"),
        name=ProductName("1 Asado Entero"),
        category=ProductCategory.POLLO_ASADO,
        price=MoneyCOP(44500),
    )
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="quiero un pollo asado con papa y yuca")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert "Papa Francesa" not in result["response_text"]
    assert "adicional de papa francesa" in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == ["ASADO_ENTERO"]
    assert "Acompanamiento asado: papa cocida y yuca incluida." in (services.session.observations or "")


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
async def test_broaster_with_default_fries_does_not_charge_french_fries() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="quiero medio broaster con papas fritas")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x 1/2 Broasted" in result["response_text"]
    assert "Papa Francesa" not in result["response_text"]
    assert "adicional de papa francesa" in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == ["BROASTER_MEDIO"]
    assert "Acompanamiento broaster: papa francesa incluida." in (services.session.observations or "")


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
async def test_paid_sauce_extra_after_cart_adds_item_instead_of_checkout_note() -> None:
    services = FakeConversationServices()
    services.session.add_cart_item(cart_item_from_product(services.products["BROASTER_ENTERO"], 1))
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="Con adicional de tártara")

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "1 x Adicional de Salsas - Tártara" in result["response_text"]
    assert "Me falta esta informacion" not in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == [
        "BROASTER_ENTERO",
        "ADICIONAL_SALSAS",
    ]


@pytest.mark.asyncio
async def test_simple_sauce_request_after_cart_stays_note_without_charge() -> None:
    services = FakeConversationServices()
    services.session.add_cart_item(cart_item_from_product(services.products["BROASTER_ENTERO"], 1))
    services.session.move_to(ConversationState.POST_ADD)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(chat_id=123, raw_text="bastante tartara")

    result = await graph.ainvoke(state)

    assert "Me falta esta informacion" in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == ["BROASTER_ENTERO"]
    assert services.session.observations == "bastante tartara"


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
    assert "Bienvenid@ a Mac Chicken" in result["response_text"]
    assert "1 x 1/2 Broasted" in result["response_text"]
    assert "1 x Sopa Adicional" in result["response_text"]
    assert "1 x Jugos Hit personal" in result["response_text"]
    assert len(services.session.cart) == 3


@pytest.mark.asyncio
async def test_new_direct_order_from_main_menu_sends_welcome_and_keeps_order_items() -> None:
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
    services.session.move_to(ConversationState.MAIN_MENU)
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="ahora quiero tambien una polla al asado con papa y yuca con una Coca-Cola 1.5",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "Bienvenid@ a Mac Chicken" in result["response_text"]
    assert "1 x 1 Asado Entero" in result["response_text"]
    assert "1 x Coca-Cola 1.5 L" in result["response_text"]
    assert "Papa Francesa" not in result["response_text"]
    assert [item.product_code.value for item in services.session.cart] == ["ASADO_ENTERO", "COCA_COLA_15"]


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
async def test_mixed_quarter_chicken_order_adds_broaster_and_asado_in_one_message() -> None:
    services = FakeConversationServices()
    graph = build_conversation_graph(services)
    state = ConversationGraphState(
        chat_id=123,
        raw_text="Me regala por favor 2 cuartos de pechuga broaster y 1 cuarto de pechuga asado",
    )

    result = await graph.ainvoke(state)

    assert result["current_step"] == ConversationState.POST_ADD
    assert "2 x 1/4 Broasted - Pechuga" in result["response_text"]
    assert "1 x 1/4 Asado - Pechuga" in result["response_text"]
    assert len(services.session.cart) == 2


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
async def test_confirm_order_with_nequi_includes_account_and_requests_proof() -> None:
    services = FakeConversationServices()
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    services.session.customer_name = "Angel David"
    services.session.customer_phone = "3153327502"
    services.session.customer_address = "Transversal 23 #52a-21"
    services.session.customer_neighborhood = "Bosquesitos"
    services.session.payment_method = "Nequi"
    services.session.move_to(ConversationState.CHECKOUT_REVIEW)
    state = ConversationGraphState(chat_id=123, raw_text="si")

    state = await nodes.confirm_order(state, services)

    assert "3182705144" in state.response_text
    assert "Fabio Leonardo Perez" in state.response_text
    assert "comprobante de pago" in state.response_text
    assert state.current_step == ConversationState.MAIN_MENU


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
async def test_checkout_review_accepts_payment_correction_and_no_cancels_order() -> None:
    services = FakeConversationServices()
    product = services.products["ASADO_MEDIO"]
    services.session.add_cart_item(cart_item_from_product(product, 1))
    services.session.customer_name = "Martin Andrés Flórez"
    services.session.customer_phone = "3142199149"
    services.session.customer_address = "Carrera 9 no 7 17"
    services.session.customer_neighborhood = "Floridablanca casco antiguo"
    services.session.payment_method = "Nequi"
    services.session.move_to(ConversationState.CHECKOUT_REVIEW)
    graph = build_conversation_graph(services)

    corrected = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="Pago en efectivo"))

    assert corrected["current_step"] == ConversationState.CHECKOUT_REVIEW
    assert "Datos recibidos" in corrected["response_text"]
    assert "Pago: Efectivo" in corrected["response_text"]
    assert "Puedes escribirme tu pedido" not in corrected["response_text"]
    assert services.session.payment_method == "Efectivo"

    cancelled = await graph.ainvoke(ConversationGraphState(chat_id=123, raw_text="no"))

    assert cancelled["current_step"] == ConversationState.MAIN_MENU
    assert services.session.cart == []
    assert "Puedes escribirme tu pedido" not in cancelled["response_text"]


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
    assert "No pude registrar tu orden" in state.response_text
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
