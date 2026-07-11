"""LangGraph node implementations for the Telegram ordering conversation.

This file is intentionally orchestration-heavy: it decides which step comes next,
but it should not know SQLAlchemy models, Redis commands or Telegram HTTP calls.
Those details stay behind ConversationGraphServices and application use cases.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.modules.ai.application.rule_based_order_parser import parse_natural_order_rules
from app.modules.catalog.domain.enums import ProductCategory
from app.modules.catalog.domain.product import Product
from app.modules.catalog.domain.specifications import ProductAvailabilitySpecification
from app.modules.conversations.application.graph_services import (
    AdminOrderCustomerPayload,
    AdminOrderItemPayload,
    AdminOrderPayload,
    ConversationGraphServices,
    cart_item_from_product,
)
from app.modules.conversations.domain.conversation_state import ConversationState
from app.modules.conversations.domain.intent import ConversationIntent
from app.modules.conversations.graph.message_factory import BotMessageFactory
from app.modules.conversations.graph.state import (
    CartLineState,
    ConversationGraphState,
    CustomerDataState,
)
from app.shared.domain.value_object import ChatId, ProductCode, ProductName
from app.shared.utils.text_normalizer import normalize_text


async def receive_message(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    return state


async def normalize_message(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    state.normalized_text = normalize_text(state.raw_text)
    return state


async def load_or_create_session(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    session = await services.load_or_create_session(ChatId(state.chat_id))
    state.current_step = session.current_step
    state.selected_product_code = (
        session.selected_product_code.value if session.selected_product_code else None
    )
    state.selected_chicken_part = session.selected_chicken_part
    state.cart = [
        CartLineState(
            product_code=item.product_code.value,
            product_name=item.product_name.value,
            unit_price_cop=item.unit_price.amount,
            quantity=item.quantity,
            subtotal_cop=item.subtotal.amount,
        )
        for item in session.cart
    ]
    state.customer = CustomerDataState(
        name=session.customer_name,
        phone=session.phone,
        address=session.address,
        neighborhood=session.neighborhood,
        payment_method=session.payment_method,
        observations=session.observations,
    )
    state.subtotal_cop = sum(line.subtotal_cop for line in state.cart)
    _copy_checkout_session_to_state(session, state)
    return state


async def detect_intent(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    text = state.normalized_text
    parsed_rules = parse_natural_order_rules(state.raw_text)
    # Navigation and numbered menus are handled before natural-language parsing.
    # This keeps the zero-cost menu flow predictable and avoids unnecessary LLM calls.
    if text in {"0", "volver", "atras", "atrás", "regresar"}:
        state.intent = ConversationIntent.VOLVER
        return state
    if state.current_step == ConversationState.POST_ADD and _is_main_menu_request(text):
        state.intent = ConversationIntent.MOSTRAR_CARRITO
        return state
    natural_menu_intent = _detect_natural_menu_intent(text)
    if natural_menu_intent is not None:
        state.intent = natural_menu_intent
        return state
    if state.current_step == ConversationState.ASK_CHICKEN_PART:
        state.selected_chicken_part = _extract_chicken_selection(state.selected_product_code, text)
        quantity = _extract_positive_integer(text)
        if (
            state.selected_chicken_part
            and quantity is not None
            and text.strip() not in {"1", "2"}
            and not _requires_chicken_composition(state.selected_product_code)
        ):
            state.intent = ConversationIntent.AGREGAR_PRODUCTO
            state.quantity = quantity
            return state
        state.intent = ConversationIntent.PEDIR_CANTIDAD
        return state
    if state.current_step == ConversationState.ASK_QUANTITY:
        state.intent = ConversationIntent.AGREGAR_PRODUCTO
        state.quantity = _extract_positive_integer(text) or 0
        return state
    if _detect_numbered_menu_intent(state):
        return state
    query = _classify_business_query(text)
    if query is not None and _looks_like_question(text):
        # Questions such as "cuanto vale medio pollo" must answer information,
        # not mutate the cart just because they mention a product.
        state.intent = ConversationIntent.RESPONDER_CONSULTA
        state.query_type = query[0]
        state.query_value = query[1]
        return state
    if parsed_rules.items:
        state.intent = ConversationIntent.LENGUAJE_NATURAL
        return state
    if state.current_step == ConversationState.POST_ADD:
        # After adding an item, short commands such as "3" or "finalizar" should
        # continue checkout instead of being interpreted as product quantities.
        if _contains_command(text, ("agregar", "agregar mas", "agregar más", "seguir", "seguir comprando")):
            state.intent = ConversationIntent.VER_MENU
            return state
        if _contains_command(text, ("carrito", "ver carrito")):
            state.intent = ConversationIntent.MOSTRAR_CARRITO
            return state
        if _contains_command(text, ("finalizar", "finalizar pedido", "checkout")):
            state.intent = ConversationIntent.PEDIR_DATOS_CLIENTE
            return state
    query = _classify_business_query(text)
    if query is not None:
        # Business questions such as prices, drink options and delivery costs are
        # answered locally from catalog/zones. Out-of-scope prompts do not spend IA.
        state.intent = ConversationIntent.RESPONDER_CONSULTA
        state.query_type = query[0]
        state.query_value = query[1]
        return state
    if text in {"menu", "menú", "hola", "inicio", "empezar"}:
        state.intent = ConversationIntent.MOSTRAR_MENU
    elif text in {"ver menu", "ver menú", "1"}:
        state.intent = ConversationIntent.VER_MENU
    elif (
        state.current_step == ConversationState.NATURAL_ORDER
        or _looks_like_natural_order(text)
        or parsed_rules.items
    ):
        state.intent = ConversationIntent.LENGUAJE_NATURAL
        return state
    elif "broaster" in text or "broasted" in text or "broster" in text:
        state.intent = ConversationIntent.MENU_BROASTER
    elif "asado" in text:
        state.intent = ConversationIntent.MENU_ASADO
    elif "bebida" in text or "gaseosa" in text:
        state.intent = ConversationIntent.MENU_BEBIDAS
    elif "adicional" in text or "papa" in text or "sopa" in text:
        state.intent = ConversationIntent.MENU_ADICIONALES
    elif "especial" in text or "lasagna" in text or "lasana" in text or "maduro" in text:
        state.intent = ConversationIntent.MENU_ESPECIALES
    elif _contains_command(
        text,
        (
            "vaciar carrito",
            "vaciar el carrito",
            "borrar carrito",
            "borrar el carrito",
            "limpiar carrito",
            "limpiar el carrito",
        ),
    ):
        state.intent = ConversationIntent.VACIAR_CARRITO
    elif _contains_command(text, ("carrito", "ver carrito", "mostrar carrito", "mi carrito")):
        state.intent = ConversationIntent.MOSTRAR_CARRITO
    elif text in {"eliminar", "quitar", "eliminar producto"}:
        state.intent = ConversationIntent.ELIMINAR_PRODUCTO
    elif text in {"finalizar", "checkout", "resumen", "finalizar pedido"}:
        state.intent = ConversationIntent.PEDIR_DATOS_CLIENTE
    elif text in {"datos", "factura"}:
        state.intent = ConversationIntent.PEDIR_DATOS_CLIENTE
    elif text in {"confirmar", "si", "sí"}:
        state.intent = ConversationIntent.CONFIRMAR_PEDIDO
    elif text in {"cancelar", "no"}:
        state.intent = ConversationIntent.CANCELAR
    elif text in {"horarios", "horario"}:
        state.intent = ConversationIntent.HORARIOS
    elif state.current_step == ConversationState.ASK_CUSTOMER_DATA:
        state.intent = ConversationIntent.PROCESAR_DATOS_CLIENTE
    else:
        state.intent = ConversationIntent.LENGUAJE_NATURAL
    return state


async def route_intent(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    return state


async def show_main_menu(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    state.current_step = ConversationState.MAIN_MENU
    state.selected_product_code = None
    state.selected_product_name = None
    state.selected_chicken_part = None
    state.selected_unit_price_cop = None
    state.quantity = None
    state.response_text = BotMessageFactory.main_menu()
    await _persist_step(state, services)
    return state


async def show_product_categories(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    state.current_step = ConversationState.PRODUCT_CATEGORY
    state.selected_product_code = None
    state.selected_product_name = None
    state.selected_chicken_part = None
    state.selected_unit_price_cop = None
    state.quantity = None
    state.response_text = BotMessageFactory.product_categories()
    await _persist_step(state, services)
    return state


async def show_asado_menu(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    return await _show_category(state, services, ProductCategory.POLLO_ASADO, ConversationState.SELECT_ASADO)


async def show_broaster_menu(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    return await _show_category(
        state,
        services,
        ProductCategory.POLLO_BROASTER,
        ConversationState.SELECT_BROASTER,
    )


async def show_drinks_menu(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    return await _show_category(state, services, ProductCategory.BEBIDAS, ConversationState.SELECT_BEBIDA)


async def show_addons_menu(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    return await _show_category(
        state,
        services,
        ProductCategory.ADICIONALES,
        ConversationState.SELECT_ADICIONAL,
    )


async def show_specials_menu(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    return await _show_category(
        state,
        services,
        ProductCategory.ESPECIALES,
        ConversationState.SELECT_ESPECIAL,
    )


async def select_product(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    product = await _find_numbered_product(state, services)
    if product is None:
        product = await services.find_product(state.normalized_text)
    if product is None:
        state.intent = ConversationIntent.PRODUCTO_INEXISTENTE
        state.response_text = BotMessageFactory.product_not_found()
        return state
    state.selected_product_code = product.code.value
    state.selected_product_name = product.name.value
    state.selected_chicken_part = None
    state.selected_unit_price_cop = product.price.amount
    return state


async def validate_product_availability(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    product_code = state.selected_product_code
    if product_code is None:
        return state
    product = await services.find_product(product_code)
    if product is None:
        state.intent = ConversationIntent.PRODUCTO_INEXISTENTE
        state.response_text = BotMessageFactory.product_not_found()
        return state
    if not _is_product_available(product):
        state.intent = ConversationIntent.PRODUCTO_RESTRINGIDO
        state.response_text = BotMessageFactory.product_unavailable()
    return state


async def ask_quantity(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    if state.selected_product_name is None or state.selected_unit_price_cop is None:
        product = await services.find_product(state.selected_product_code or "")
        if product is None:
            return await fallback_natural_language(state, services)
        state.selected_product_name = product.name.value
        state.selected_unit_price_cop = product.price.amount
    if _requires_chicken_selection(state.selected_product_code) and not state.selected_chicken_part:
        state.current_step = ConversationState.ASK_CHICKEN_PART
        state.response_text = _ask_chicken_selection_message(
            state.selected_product_code,
            state.selected_product_name,
        )
        await _persist_step(state, services)
        return state
    state.current_step = ConversationState.ASK_QUANTITY
    state.response_text = BotMessageFactory.ask_quantity(
        _display_product_name(state.selected_product_name, state.selected_chicken_part),
        state.selected_unit_price_cop,
    )
    await _persist_step(state, services)
    return state


async def add_to_cart(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    if state.selected_product_code is None or state.quantity is None or state.quantity <= 0:
        state.response_text = BotMessageFactory.invalid_quantity()
        return state
    session = await services.load_or_create_session(ChatId(state.chat_id))
    product = await services.find_product(state.selected_product_code)
    if product is None:
        state.response_text = BotMessageFactory.product_not_found()
        return state
    if state.selected_chicken_part:
        session.selected_chicken_part = state.selected_chicken_part
    item = _cart_item_from_selected_product(
        product,
        state.quantity,
        session.selected_chicken_part,
    )
    session.add_cart_item(item)
    session.clear_selected_product()
    session.move_to(ConversationState.POST_ADD)
    await services.persist_session(session)
    line = CartLineState(
        product_code=item.product_code.value,
        product_name=item.product_name.value,
        unit_price_cop=item.unit_price.amount,
        quantity=item.quantity,
        subtotal_cop=item.subtotal.amount,
    )
    state.cart.append(line)
    state.subtotal_cop = sum(cart_line.subtotal_cop for cart_line in state.cart)
    state.current_step = ConversationState.POST_ADD
    state.response_text = BotMessageFactory.added_to_cart(line, state.subtotal_cop)
    return state


async def show_cart(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    state.subtotal_cop = sum(line.subtotal_cop for line in state.cart)
    if state.cart:
        state.current_step = ConversationState.POST_ADD
    state.response_text = BotMessageFactory.cart(state.cart, state.subtotal_cop)
    await _persist_step(state, services)
    return state


async def clear_cart(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    session = await services.load_or_create_session(ChatId(state.chat_id))
    session.empty_cart()
    session.move_to(ConversationState.MAIN_MENU)
    await services.persist_session(session)
    state.cart = []
    state.subtotal_cop = 0
    state.current_step = ConversationState.MAIN_MENU
    state.response_text = BotMessageFactory.clear_cart()
    return state


async def remove_last_item(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    session = await services.load_or_create_session(ChatId(state.chat_id))
    removed = session.remove_last_cart_item()
    await services.persist_session(session)
    if state.cart:
        state.cart.pop()
    state.subtotal_cop = sum(line.subtotal_cop for line in state.cart)
    state.response_text = BotMessageFactory.remove_last_item(
        removed.product_name.value if removed else None
    )
    return state


async def prepare_checkout_summary(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    state.current_step = ConversationState.CHECKOUT_CONFIRM
    state.subtotal_cop = sum(line.subtotal_cop for line in state.cart)
    state.response_text = BotMessageFactory.checkout_summary(state)
    await _persist_step(state, services)
    return state


async def ask_customer_data(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    if not state.cart:
        state.current_step = ConversationState.PRODUCT_CATEGORY
        state.response_text = BotMessageFactory.checkout_summary(state)
        await _persist_step(state, services)
        return state
    state.current_step = ConversationState.ASK_CUSTOMER_DATA
    state.response_text = BotMessageFactory.ask_customer_data()
    await _persist_step(state, services)
    return state


async def extract_customer_data(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    # Copy nested Pydantic state before mutating it. LangGraph can reuse state
    # objects between nodes, so direct nested mutation is easy to lose or leak.
    customer = state.customer.model_copy(deep=True)
    free_lines: list[str] = []
    for line in state.raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" not in line:
            free_lines.append(line)
            continue
        key, value = line.split(":", 1)
        key = normalize_text(key)
        value = value.strip()
        if key in {"nombre", "nombre completo", "cliente"}:
            customer.name = value
        elif key in {"telefono", "celular"}:
            customer.phone = value
        elif key in {"direccion", "dir"}:
            customer.address = value
        elif key in {"barrio", "sector"}:
            customer.neighborhood = value
        elif key in {"metodo de pago", "pago", "medio de pago", "forma de pago"}:
            customer.payment_method = value
        elif key in {
            "observaciones",
            "observacion",
            "notas",
            "nota",
            "nota o especificacion",
            "especificacion",
        }:
            customer.observations = value
    if free_lines:
        _extract_customer_data_from_free_lines(customer, free_lines)
    state.customer = customer
    return state


async def validate_customer_data(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    missing: list[str] = []
    if not state.customer.name:
        missing.append("nombre completo")
    if not state.customer.phone:
        missing.append("telefono")
    if not state.customer.address:
        missing.append("direccion")
    if not state.customer.neighborhood:
        missing.append("barrio")
    if not state.customer.payment_method:
        missing.append("metodo de pago")
    if missing:
        state.errors = missing
        state.current_step = ConversationState.ASK_CUSTOMER_DATA
        session = await services.load_or_create_session(ChatId(state.chat_id))
        _copy_checkout_state_to_session(state, session)
        session.move_to(ConversationState.ASK_CUSTOMER_DATA)
        await services.persist_session(session)
        state.response_text = BotMessageFactory.missing_customer_data(missing)
    else:
        state.current_step = ConversationState.CHECKOUT_REVIEW
        session = await services.load_or_create_session(ChatId(state.chat_id))
        _copy_checkout_state_to_session(state, session)
        session.move_to(ConversationState.CHECKOUT_REVIEW)
        await services.persist_session(session)
    return state


def _extract_customer_data_from_free_lines(
    customer: CustomerDataState,
    lines: list[str],
) -> None:
    # Customers usually send checkout data as loose lines, not as a strict form.
    # Detect strong signals first, then assign the remaining human text by order.
    remaining: list[str] = []
    for line in lines:
        normalized = normalize_text(line)
        if not customer.address and _looks_like_address(normalized):
            customer.address = line
        elif not customer.phone and _looks_like_phone(line):
            customer.phone = line
        elif not customer.payment_method and _looks_like_payment_method(normalized):
            customer.payment_method = _normalize_payment_method(normalized, line)
        else:
            remaining.append(line)

    if not customer.name and remaining:
        customer.name = remaining.pop(0)
    if not customer.observations and remaining and _looks_like_empty_note(normalize_text(remaining[0])):
        customer.observations = remaining.pop(0)
    if not customer.neighborhood and remaining:
        customer.neighborhood = remaining.pop(0)
    if not customer.observations and remaining:
        customer.observations = " ".join(remaining)


def _looks_like_phone(text: str) -> bool:
    if _looks_like_address(normalize_text(text)):
        return False
    digits = re.sub(r"\D", "", text)
    return 7 <= len(digits) <= 10


def _looks_like_address(normalized: str) -> bool:
    address_markers = {
        "cra",
        "carrera",
        "calle",
        "cll",
        "cl",
        "avenida",
        "av",
        "transversal",
        "tv",
        "diagonal",
        "dg",
        "manzana",
        "mz",
        "casa",
        "apto",
        "apartamento",
        "#",
    }
    tokens = set(normalized.replace("#", " # ").split())
    return bool(tokens & address_markers) or ("#" in normalized and any(ch.isdigit() for ch in normalized))


def _looks_like_payment_method(normalized: str) -> bool:
    return any(
        word in normalized
        for word in [
            "efectivo",
            "datafono",
            "datáfono",
            "nequi",
            "transferencia",
            "bancolombia",
        ]
    )


def _looks_like_empty_note(normalized: str) -> bool:
    return normalized in {
        "ninguna",
        "ninguno",
        "sin nota",
        "sin notas",
        "sin observacion",
        "sin observaciones",
        "no",
        "n/a",
        "na",
    }


def _normalize_payment_method(normalized: str, original: str) -> str:
    if "nequi" in normalized:
        return "Nequi"
    if "datafono" in normalized or "datáfono" in normalized:
        return "Datafono"
    if "transferencia" in normalized or "bancolombia" in normalized:
        return "Transferencia Bancolombia"
    if "efectivo" in normalized:
        return "Efectivo"
    return original


def _copy_checkout_state_to_session(
    state: ConversationGraphState,
    session,
) -> None:
    session.customer_name = state.customer.name
    session.customer_phone = state.customer.phone
    session.customer_address = state.customer.address
    session.customer_neighborhood = state.customer.neighborhood
    session.payment_method = state.customer.payment_method
    session.observations = state.customer.observations


def _copy_checkout_session_to_state(
    session,
    state: ConversationGraphState,
) -> None:
    customer = state.customer.model_copy(deep=True)
    customer.name = customer.name or session.customer_name
    customer.phone = customer.phone or session.customer_phone
    customer.address = customer.address or session.customer_address
    customer.neighborhood = customer.neighborhood or session.customer_neighborhood
    customer.payment_method = customer.payment_method or session.payment_method
    customer.observations = customer.observations or session.observations
    state.customer = customer


def _clear_checkout_session(session) -> None:
    session.customer_name = None
    session.customer_phone = None
    session.customer_address = None
    session.customer_neighborhood = None
    session.payment_method = None
    session.observations = None


def _admin_order_payload_from_state(state: ConversationGraphState) -> AdminOrderPayload:
    return AdminOrderPayload(
        external_bot_id=f"whatsapp-{state.chat_id}-{datetime.now(ZoneInfo('UTC')).isoformat()}",
        chat_id=str(state.chat_id),
        customer=AdminOrderCustomerPayload(
            full_name=state.customer.name or "",
            phone=state.customer.phone or "",
            address=" - ".join(
                part
                for part in [state.customer.address, state.customer.neighborhood]
                if part
            )
            or "",
        ),
        payment_method=state.customer.payment_method or "",
        observations=state.customer.observations,
        delivery_fee_cop=state.delivery_price_cop or 0,
        items=[
            AdminOrderItemPayload(
                product_code=item.product_code,
                product_name=item.product_name,
                quantity=item.quantity,
                unit_price_cop=item.unit_price_cop,
            )
            for item in state.cart
        ],
    )


async def calculate_delivery(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    # Delivery calculation may use manual zones or ORS distance behind the service.
    # The graph only stores the resulting integer COP price in conversation state.
    if state.customer.address and state.customer.neighborhood:
        result = await services.calculate_delivery(
            address=state.customer.address,
            neighborhood=state.customer.neighborhood,
        )
        state.delivery_price_cop = result.delivery_price_cop
    else:
        state.delivery_price_cop = state.delivery_price_cop or 0
    state.subtotal_cop = sum(line.subtotal_cop for line in state.cart)
    state.total_cop = state.subtotal_cop + state.delivery_price_cop
    return state


async def create_order(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    state.response_text = BotMessageFactory.order_created(state)
    state.current_step = ConversationState.CHECKOUT_REVIEW
    session = await services.load_or_create_session(ChatId(state.chat_id))
    _copy_checkout_state_to_session(state, session)
    session.move_to(state.current_step)
    await services.persist_session(session)
    return state


async def confirm_order(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    session = await services.load_or_create_session(ChatId(state.chat_id))
    _copy_checkout_session_to_state(session, state)
    state.cart = [
        CartLineState(
            product_code=item.product_code.value,
            product_name=item.product_name.value,
            unit_price_cop=item.unit_price.amount,
            quantity=item.quantity,
            subtotal_cop=item.subtotal.amount,
        )
        for item in session.cart
    ]
    state.subtotal_cop = sum(line.subtotal_cop for line in state.cart)
    missing = _missing_checkout_fields(state)
    if missing:
        state.errors = missing
        state.current_step = ConversationState.ASK_CUSTOMER_DATA
        state.response_text = BotMessageFactory.missing_customer_data(missing)
        _copy_checkout_state_to_session(state, session)
        session.move_to(ConversationState.ASK_CUSTOMER_DATA)
        await services.persist_session(session)
        return state
    if state.customer.address and state.customer.neighborhood:
        delivery = await services.calculate_delivery(
            address=state.customer.address,
            neighborhood=state.customer.neighborhood,
        )
        state.delivery_price_cop = delivery.delivery_price_cop
    try:
        await services.sync_confirmed_order(_admin_order_payload_from_state(state))
    except Exception:
        state.current_step = ConversationState.CHECKOUT_REVIEW
        state.response_text = BotMessageFactory.order_confirmation_failed()
        await _persist_step(state, services)
        return state
    session.empty_cart()
    session.clear_selected_product()
    _clear_checkout_session(session)
    session.move_to(ConversationState.MAIN_MENU)
    await services.persist_session(session)
    state.current_step = ConversationState.MAIN_MENU
    state.cart = []
    state.customer = CustomerDataState()
    state.subtotal_cop = 0
    state.total_cop = 0
    state.response_text = BotMessageFactory.confirmed()
    return state


def _missing_checkout_fields(state: ConversationGraphState) -> list[str]:
    missing: list[str] = []
    if not state.cart:
        missing.append("productos")
    if not state.customer.name:
        missing.append("nombre completo")
    if not state.customer.phone:
        missing.append("telefono")
    if not state.customer.address:
        missing.append("direccion")
    if not state.customer.neighborhood:
        missing.append("barrio")
    if not state.customer.payment_method:
        missing.append("metodo de pago")
    return missing


async def cancel_order(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    session = await services.load_or_create_session(ChatId(state.chat_id))
    session.empty_cart()
    session.clear_selected_product()
    session.clear_customer_data()
    session.move_to(ConversationState.MAIN_MENU)
    await services.persist_session(session)
    state.current_step = ConversationState.MAIN_MENU
    state.cart = []
    state.customer = CustomerDataState()
    state.response_text = BotMessageFactory.cancelled()
    return state


async def send_telegram_response(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    state.should_send_response = bool(state.response_text)
    return state


async def fallback_natural_language(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    if state.normalized_text not in {"2", "4", "pedido libre", "pedido libremente"}:
        added_lines = await _add_natural_order_to_cart(state, services)
        if added_lines:
            state.current_step = ConversationState.POST_ADD
            state.subtotal_cop = sum(line.subtotal_cop for line in state.cart)
            state.response_text = BotMessageFactory.natural_order_added(
                added_lines,
                state.subtotal_cop,
            )
            return state
        if state.response_text:
            return state
        if _looks_like_natural_order(state.normalized_text):
            state.current_step = ConversationState.PRODUCT_CATEGORY
            state.response_text = BotMessageFactory.unavailable_product_answer()
            await _persist_step(state, services)
            return state

    state.current_step = ConversationState.NATURAL_ORDER
    state.response_text = BotMessageFactory.natural_language_fallback()
    await _persist_step(state, services)
    return state


async def show_schedules(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    state.response_text = BotMessageFactory.schedules()
    return state


async def answer_query(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    if state.query_type == "order_status":
        state.response_text = BotMessageFactory.order_status_answer()
        return state
    if state.query_type == "category":
        category = _category_from_query_value(state.query_value or "")
        if category is not None:
            products = await services.list_products_by_category(category)
            state.response_text = BotMessageFactory.product_list_answer(category.value, products)
            return state
    if state.query_type == "price":
        product = await _find_product_for_query(state.query_value or state.raw_text, services)
        if product is not None:
            state.response_text = BotMessageFactory.product_price_answer(product)
            return state
    if state.query_type == "delivery":
        neighborhood = state.query_value or _extract_delivery_neighborhood(state.normalized_text)
        if neighborhood:
            result = await services.calculate_delivery(address="", neighborhood=neighborhood)
            state.response_text = BotMessageFactory.delivery_price_answer(
                neighborhood,
                result.delivery_price_cop,
            )
            return state
    state.response_text = BotMessageFactory.business_unknown_answer()
    return state


async def go_back(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> ConversationGraphState:
    if state.current_step in {
        ConversationState.SELECT_ASADO,
        ConversationState.SELECT_BROASTER,
        ConversationState.SELECT_BEBIDA,
        ConversationState.SELECT_ADICIONAL,
        ConversationState.SELECT_ESPECIAL,
        ConversationState.ASK_CHICKEN_PART,
        ConversationState.ASK_QUANTITY,
        ConversationState.POST_ADD,
    }:
        return await show_product_categories(state, services)
    if state.current_step in {
        ConversationState.ASK_CUSTOMER_DATA,
        ConversationState.CHECKOUT_CONFIRM,
        ConversationState.CHECKOUT_REVIEW,
    }:
        return await show_cart(state, services)
    return await show_main_menu(state, services)


async def _show_category(
    state: ConversationGraphState,
    services: ConversationGraphServices,
    category: ProductCategory,
    next_step: ConversationState,
) -> ConversationGraphState:
    products = await services.list_products_by_category(category)
    state.current_step = next_step
    state.response_text = BotMessageFactory.product_menu(category.value, products)
    await _persist_step(state, services)
    return state


def _detect_numbered_menu_intent(state: ConversationGraphState) -> bool:
    text = state.normalized_text
    if not text.isdigit():
        return False

    if state.current_step == ConversationState.POST_ADD:
        post_add_routes = {
            "1": ConversationIntent.VER_MENU,
            "2": ConversationIntent.MOSTRAR_CARRITO,
            "3": ConversationIntent.PEDIR_DATOS_CLIENTE,
            "4": ConversationIntent.VACIAR_CARRITO,
        }
        if text in post_add_routes:
            state.intent = post_add_routes[text]
            return True

    if state.current_step == ConversationState.MAIN_MENU:
        main_menu_routes = {
            "1": ConversationIntent.VER_MENU,
            "2": ConversationIntent.LENGUAJE_NATURAL,
            "3": ConversationIntent.MOSTRAR_CARRITO,
            "4": ConversationIntent.HORARIOS,
        }
        state.intent = main_menu_routes.get(text, ConversationIntent.LENGUAJE_NATURAL)
        return True

    if state.current_step == ConversationState.PRODUCT_CATEGORY:
        category_routes = {
            "1": ConversationIntent.MENU_ASADO,
            "2": ConversationIntent.MENU_BROASTER,
            "3": ConversationIntent.MENU_BEBIDAS,
            "4": ConversationIntent.MENU_ADICIONALES,
            "5": ConversationIntent.MENU_ESPECIALES,
            "6": ConversationIntent.PEDIR_DATOS_CLIENTE,
        }
        state.intent = category_routes.get(text, ConversationIntent.LENGUAJE_NATURAL)
        return True

    if state.current_step == ConversationState.ASK_QUANTITY:
        state.intent = ConversationIntent.AGREGAR_PRODUCTO
        state.quantity = int(text)
        return True

    if state.current_step in {
        ConversationState.SELECT_ASADO,
        ConversationState.SELECT_BROASTER,
        ConversationState.SELECT_BEBIDA,
        ConversationState.SELECT_ADICIONAL,
        ConversationState.SELECT_ESPECIAL,
    }:
        state.intent = ConversationIntent.LENGUAJE_NATURAL
        return True

    return False


async def _add_natural_order_to_cart(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> list[CartLineState]:
    parsed = parse_natural_order_rules(state.raw_text)
    if not parsed.items:
        return []

    session = await services.load_or_create_session(ChatId(state.chat_id))
    added_lines: list[CartLineState] = []
    restricted_product_name: str | None = None
    for item in parsed.items:
        product = await services.find_product(item.code)
        if product is None:
            continue
        if not _is_product_available(product):
            restricted_product_name = product.name.value
            continue
        chicken_part = _extract_chicken_selection(item.code, state.normalized_text)
        if _requires_chicken_selection(item.code) and not chicken_part:
            session.selected_product_code = product.code
            session.selected_chicken_part = None
            session.move_to(ConversationState.ASK_CHICKEN_PART)
            await services.persist_session(session)
            state.selected_product_code = product.code.value
            state.selected_product_name = product.name.value
            state.selected_unit_price_cop = product.price.amount
            state.selected_chicken_part = None
            state.current_step = ConversationState.ASK_CHICKEN_PART
            state.response_text = _ask_chicken_selection_message(item.code, product.name.value)
            return []
        cart_item = _cart_item_from_selected_product(product, item.quantity, chicken_part)
        session.add_cart_item(cart_item)
        line = CartLineState(
            product_code=cart_item.product_code.value,
            product_name=cart_item.product_name.value,
            unit_price_cop=cart_item.unit_price.amount,
            quantity=cart_item.quantity,
            subtotal_cop=cart_item.subtotal.amount,
        )
        state.cart.append(line)
        added_lines.append(line)

    if not added_lines:
        if restricted_product_name:
            state.intent = ConversationIntent.PRODUCTO_RESTRINGIDO
            state.response_text = BotMessageFactory.product_unavailable()
        return []
    session.clear_selected_product()
    session.move_to(ConversationState.POST_ADD)
    await services.persist_session(session)
    return added_lines


def _looks_like_natural_order(text: str) -> bool:
    return any(
        phrase in text
        for phrase in [
            "quiero",
            "necesito",
            "dame",
            "me das",
            "me da",
            "me regala",
            "me regalas",
            "me puede regalar",
            "me puedes regalar",
            "regalame",
            "regálame",
            "me vende",
            "me vendes",
            "agrega",
            "agregar",
            "pideme",
            "pídeme",
            "pedido",
            "tambien",
            "también",
        ]
    )


def _detect_natural_menu_intent(text: str) -> ConversationIntent | None:
    if _is_main_menu_request(text):
        return ConversationIntent.MOSTRAR_MENU
    if _contains_command(text, ("finalizar", "finalizar pedido", "terminar pedido", "checkout")):
        return ConversationIntent.PEDIR_DATOS_CLIENTE
    if _contains_command(
        text,
        (
            "vaciar carrito",
            "vaciar el carrito",
            "borrar carrito",
            "borrar el carrito",
            "limpiar carrito",
            "limpiar el carrito",
        ),
    ):
        return ConversationIntent.VACIAR_CARRITO
    if _contains_command(text, ("ver carrito", "mostrar carrito", "mi carrito", "carrito")):
        return ConversationIntent.MOSTRAR_CARRITO
    if _contains_command(text, ("quitar producto", "eliminar producto", "quitar ultimo", "quitar último")):
        return ConversationIntent.ELIMINAR_PRODUCTO
    if _contains_command(text, ("horario", "horarios", "a que hora", "a qué hora")):
        return ConversationIntent.HORARIOS
    if _contains_command(text, ("pedir escribiendo", "pedido libre", "escribir pedido")):
        return ConversationIntent.LENGUAJE_NATURAL
    if _is_category_request(text, ("pollo asado", "menu asado", "menú asado", "asado")):
        return ConversationIntent.MENU_ASADO
    if _is_category_request(text, ("broaster", "broasted", "broster")):
        return ConversationIntent.MENU_BROASTER
    if _is_category_request(text, ("bebida", "bebidas", "gaseosa", "gaseosas")):
        return ConversationIntent.MENU_BEBIDAS
    if _is_category_request(text, ("adicional", "adicionales", "papa", "papas", "sopa")):
        return ConversationIntent.MENU_ADICIONALES
    if _is_category_request(text, ("especial", "especiales", "platos especiales")):
        return ConversationIntent.MENU_ESPECIALES
    if _is_menu_request(text):
        return ConversationIntent.VER_MENU
    return None


def _contains_command(text: str, commands: tuple[str, ...]) -> bool:
    if _contains_any(text, commands):
        return True
    text_tokens = text.split()
    for command in commands:
        command_tokens = normalize_text(command).split()
        if not command_tokens or len(command_tokens) > len(text_tokens):
            continue
        for index in range(len(text_tokens) - len(command_tokens) + 1):
            window = text_tokens[index : index + len(command_tokens)]
            if all(_is_close_word(word, expected) for word, expected in zip(window, command_tokens)):
                return True
    return False


def _is_close_word(value: str, expected: str) -> bool:
    if value == expected:
        return True
    if len(expected) <= 3:
        return False
    return SequenceMatcher(None, value, expected).ratio() >= 0.78


def _is_main_menu_request(text: str) -> bool:
    return text in {"hola", "inicio", "empezar"} or _contains_any(
        text,
        (
            "hola buenas",
            "buenas",
            "menu principal",
            "menú principal",
            "menu inicial",
            "menú inicial",
            "menu de inicio",
            "menú de inicio",
            "inicio",
        ),
    )


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _requires_chicken_selection(product_code: str | None) -> bool:
    return _requires_chicken_part(product_code) or _requires_chicken_composition(product_code)


def _requires_chicken_part(product_code: str | None) -> bool:
    return product_code in {"ASADO_CUARTO", "BROASTER_CUARTO"}


def _requires_chicken_composition(product_code: str | None) -> bool:
    return product_code in {"ASADO_34", "BROASTER_34"}


def _ask_chicken_selection_message(product_code: str | None, product_name: str) -> str:
    if _requires_chicken_composition(product_code):
        return BotMessageFactory.ask_chicken_composition(product_name)
    return BotMessageFactory.ask_chicken_part(product_name)


def _extract_chicken_selection(product_code: str | None, text: str) -> str | None:
    if _requires_chicken_composition(product_code):
        return _extract_chicken_composition(text)
    return _extract_chicken_part(text)


def _extract_chicken_part(text: str) -> str | None:
    if text.strip() == "1":
        return "Pierna"
    if text.strip() == "2":
        return "Pechuga"
    tokens = text.split()
    for token in tokens:
        if _is_close_word(token, "pierna") or _is_close_word(token, "muslo"):
            return "Pierna"
        if _is_close_word(token, "pechuga") or _is_close_word(token, "pechga"):
            return "Pechuga"
    return None


def _extract_chicken_composition(text: str) -> str | None:
    cleaned = text.strip()
    if cleaned == "1":
        return "2 piernas y 1 pechuga"
    if cleaned == "2":
        return "2 pechugas y 1 pierna"
    if _mentions_count(text, "pierna", 2) and _mentions_count(text, "pechuga", 1):
        return "2 piernas y 1 pechuga"
    if _mentions_count(text, "pechuga", 2) and _mentions_count(text, "pierna", 1):
        return "2 pechugas y 1 pierna"
    return None


def _mentions_count(text: str, word: str, count: int) -> bool:
    count_words = {
        1: ("1", "una", "un"),
        2: ("2", "dos"),
    }
    tokens = text.split()
    for index, token in enumerate(tokens):
        if not _is_close_word(token, word):
            continue
        nearby = tokens[max(0, index - 2) : index]
        if any(value in count_words[count] for value in nearby):
            return True
    return False


def _extract_positive_integer(text: str) -> int | None:
    match = re.search(r"\b([1-9]\d*)\b", text)
    if match is not None:
        return int(match.group(1))
    tokens = text.split()
    number_words = {
        "un": 1,
        "una": 1,
        "uno": 1,
        "dos": 2,
        "tres": 3,
        "cuatro": 4,
        "cinco": 5,
        "seis": 6,
        "siete": 7,
        "ocho": 8,
        "nueve": 9,
        "diez": 10,
    }
    for token in tokens:
        value = number_words.get(token)
        if value is not None:
            return value
    return None


def _display_product_name(product_name: str, chicken_part: str | None) -> str:
    if not chicken_part:
        return product_name
    return f"{product_name} - {chicken_part}"


def _cart_item_from_selected_product(product: Product, quantity: int, chicken_part: str | None):
    item = cart_item_from_product(product, quantity)
    if not chicken_part:
        return item
    return type(item)(
        product_code=item.product_code,
        product_name=ProductName(_display_product_name(item.product_name.value, chicken_part)),
        unit_price=item.unit_price,
        quantity=item.quantity,
    )


def _is_category_request(text: str, category_terms: tuple[str, ...]) -> bool:
    action_terms = ("menu", "menú", "ver", "mostrar", "opciones", "categoria", "categoría")
    return _contains_any(text, action_terms) and _contains_any(text, category_terms)


def _business_today() -> date:
    return datetime.now(ZoneInfo("America/Bogota")).date()


def _is_product_available(product: Product, business_date: date | None = None) -> bool:
    availability = ProductAvailabilitySpecification(is_holiday=lambda _: False)
    return availability.is_satisfied_by(product, business_date or _business_today())


def _is_menu_request(text: str) -> bool:
    if text in {"menu", "menú"}:
        return False
    return "menu" in text or "menú" in text


def _classify_business_query(text: str) -> tuple[str, str] | None:
    if _is_out_of_scope_query(text):
        return ("unknown", text)
    if _looks_like_order_status_query(text):
        return ("order_status", text)
    short_product_reference = _short_product_reference(text)
    if short_product_reference:
        return ("price", short_product_reference)
    if not _looks_like_question(text):
        return None
    if any(word in text for word in ["domicilio", "envio", "envío", "llevar", "lleva"]):
        neighborhood = _extract_delivery_neighborhood(text)
        return ("delivery", neighborhood or text)
    if any(word in text for word in ["vale", "valor", "precio", "cuanto cuesta", "cuánto cuesta"]):
        if any(word in text for word in ["gaseosa", "gaseosas", "bebida", "bebidas", "coca"]):
            return ("category", "bebidas")
        return ("price", text)
    if any(word in text for word in ["tienes", "tiene", "hay", "venden", "manejan"]):
        if any(word in text for word in ["gaseosa", "gaseosas", "bebida", "bebidas", "coca"]):
            return ("category", "bebidas")
        if any(word in text for word in ["adicional", "adicionales", "papas", "sopa"]):
            return ("category", "adicionales")
        if any(word in text for word in ["asado", "pollo asado"]):
            return ("category", "asado")
        if any(word in text for word in ["broaster", "broasted", "broster"]):
            return ("category", "broaster")
        if any(word in text for word in ["especial", "especiales", "lasagna", "maduro"]):
            return ("category", "especiales")
    return None


def _looks_like_order_status_query(text: str) -> bool:
    status_terms = (
        "demora",
        "demorar",
        "demorado",
        "tarda",
        "tardar",
        "llega",
        "llegar",
        "despacho",
        "despachar",
        "pedido",
        "como va",
        "cómo va",
    )
    product_terms = ("pollo", "pedido", "domicilio", "comida")
    return _contains_any(text, status_terms) and _contains_any(text, product_terms)


def _short_product_reference(text: str) -> str:
    cleaned = text.strip(" ¿?.,!¡")
    if cleaned in {"la 1.5", "1.5", "1,5", "litro y medio", "litro medio"}:
        return "coca cola 1.5"
    if cleaned in {"agua", "aguita", "botella de agua"}:
        return "agua botella"
    if cleaned in {"personal", "la personal", "400", "400 ml"}:
        return "personal 400"
    if cleaned in {"lata", "la lata"}:
        return "lata gaseosa"
    return ""


def _looks_like_question(text: str) -> bool:
    return any(
        word in text
        for word in [
            "que",
            "qué",
            "cuanto",
            "cuánto",
            "cual",
            "cuál",
            "tienes",
            "tiene",
            "hay",
            "vale",
            "precio",
            "valor",
            "domicilio",
        ]
    )


def _is_out_of_scope_query(text: str) -> bool:
    return any(
        phrase in text
        for phrase in [
            "hola mundo",
            "python",
            "javascript",
            "programa",
            "codigo",
            "código",
            "receta",
            "tarea",
            "chiste",
        ]
    )


def _extract_delivery_neighborhood(text: str) -> str:
    patterns = [
        r"(?:domicilio|envio|envío|llevar|lleva)(?:\s+para|\s+a|\s+hasta|\s+en)?\s+(.+)",
        r"(?:para|a|hasta|en)\s+(.+?)\s+(?:cuanto|cuánto|vale|cuesta)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = match.group(1).strip(" ?.,")
            value = re.sub(r"\b(cuanto|cuánto|vale|cuesta|es|el|la|un|una)\b", "", value).strip()
            if value:
                return value
    return ""


def _category_from_query_value(value: str) -> ProductCategory | None:
    mapping = {
        "bebidas": ProductCategory.BEBIDAS,
        "adicionales": ProductCategory.ADICIONALES,
        "asado": ProductCategory.POLLO_ASADO,
        "broaster": ProductCategory.POLLO_BROASTER,
        "especiales": ProductCategory.ESPECIALES,
    }
    return mapping.get(value)


async def _find_product_for_query(
    text: str,
    services: ConversationGraphServices,
):
    parsed = parse_natural_order_rules(text)
    for item in parsed.items:
        product = await services.find_product(item.code)
        if product is not None:
            return product
    normalized = normalize_text(text)
    for removable in [
        "cuanto vale",
        "cuánto vale",
        "cuanto cuesta",
        "cuánto cuesta",
        "precio de",
        "valor de",
        "que vale",
        "qué vale",
        "vale",
    ]:
        normalized = normalized.replace(removable, " ")
    return await services.find_product(normalized.strip())


async def _find_numbered_product(
    state: ConversationGraphState,
    services: ConversationGraphServices,
):
    if not state.normalized_text.isdigit():
        return None
    category_by_step = {
        ConversationState.SELECT_ASADO: ProductCategory.POLLO_ASADO,
        ConversationState.SELECT_BROASTER: ProductCategory.POLLO_BROASTER,
        ConversationState.SELECT_BEBIDA: ProductCategory.BEBIDAS,
        ConversationState.SELECT_ADICIONAL: ProductCategory.ADICIONALES,
        ConversationState.SELECT_ESPECIAL: ProductCategory.ESPECIALES,
    }
    category = category_by_step.get(state.current_step)
    if category is None:
        return None
    index = int(state.normalized_text) - 1
    products = await services.list_products_by_category(category)
    if index < 0 or index >= len(products):
        return None
    return products[index]


async def _persist_step(
    state: ConversationGraphState,
    services: ConversationGraphServices,
) -> None:
    session = await services.load_or_create_session(ChatId(state.chat_id))
    if state.current_step in {ConversationState.MAIN_MENU, ConversationState.PRODUCT_CATEGORY}:
        session.clear_selected_product()
    elif state.selected_product_code:
        session.selected_product_code = ProductCode(state.selected_product_code)
    else:
        session.clear_selected_product()
    session.selected_chicken_part = state.selected_chicken_part
    session.update_customer_data(
        customer_name=state.customer.name,
        phone=state.customer.phone,
        address=state.customer.address,
        neighborhood=state.customer.neighborhood,
        payment_method=state.customer.payment_method,
        observations=state.customer.observations,
    )
    await services.persist_step(session, state.current_step)
