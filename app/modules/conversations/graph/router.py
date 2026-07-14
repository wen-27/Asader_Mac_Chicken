"""Routing decisions for the LangGraph conversation.

Routers translate detected intents and state flags into node names. Keep this
file declarative so future developers can see the conversation paths quickly.
"""

from __future__ import annotations

from app.modules.conversations.domain.intent import ConversationIntent
from app.modules.conversations.domain.conversation_state import ConversationState
from app.modules.conversations.graph.state import ConversationGraphState


def _value(state: ConversationGraphState | dict, key: str):
    if isinstance(state, dict):
        return state.get(key)
    return getattr(state, key)


def route_after_intent(state: ConversationGraphState) -> str:
    # Explicit intents win first. If an intent is missing here, the graph falls
    # back to product selection only while the user is inside a category menu.
    if _value(state, "intent") == ConversationIntent.LENGUAJE_NATURAL:
        current_step = _value(state, "current_step")
        normalized_text = (_value(state, "normalized_text") or "").strip()
        if current_step in {
            ConversationState.SELECT_ASADO,
            ConversationState.SELECT_BROASTER,
            ConversationState.SELECT_BEBIDA,
            ConversationState.SELECT_ADICIONAL,
            ConversationState.SELECT_ESPECIAL,
        } and normalized_text.isdigit():
            return "select_product"
        return "fallback_natural_language"
    routes = {
        ConversationIntent.MOSTRAR_MENU: "show_main_menu",
        ConversationIntent.VER_MENU: "show_product_categories",
        ConversationIntent.MENU_ASADO: "show_asado_menu",
        ConversationIntent.MENU_BROASTER: "show_broaster_menu",
        ConversationIntent.MENU_BEBIDAS: "show_drinks_menu",
        ConversationIntent.MENU_ADICIONALES: "show_addons_menu",
        ConversationIntent.MENU_ESPECIALES: "show_specials_menu",
        ConversationIntent.MOSTRAR_CARRITO: "show_cart",
        ConversationIntent.VACIAR_CARRITO: "clear_cart",
        ConversationIntent.ELIMINAR_PRODUCTO: "remove_last_item",
        ConversationIntent.RESUMEN_CHECKOUT: "prepare_checkout_summary",
        ConversationIntent.PEDIR_DATOS_CLIENTE: "ask_customer_data",
        ConversationIntent.PROCESAR_DATOS_CLIENTE: "extract_customer_data",
        ConversationIntent.CONFIRMAR_PEDIDO: "confirm_order",
        ConversationIntent.CANCELAR: "cancel_order",
        ConversationIntent.HORARIOS: "show_schedules",
        ConversationIntent.FUERA_HORARIO: "show_outside_business_hours",
        ConversationIntent.INICIAR_DOMICILIO: "start_delivery_order",
        ConversationIntent.PEDIR_CANTIDAD: "ask_quantity",
        ConversationIntent.AGREGAR_PRODUCTO: "add_to_cart",
        ConversationIntent.AGREGAR_MEDIO_COMBO: "add_half_combo_to_cart",
        ConversationIntent.CONTINUAR_SIN_SOPA: "continue_without_soup",
        ConversationIntent.VOLVER: "go_back",
        ConversationIntent.RESPONDER_CONSULTA: "answer_query",
        ConversationIntent.PRODUCTO_RESTRINGIDO: "send_telegram_response",
        ConversationIntent.PRODUCTO_INEXISTENTE: "send_telegram_response",
    }
    route = routes.get(_value(state, "intent"))
    if route is not None:
        return route
    if _value(state, "current_step") not in {
        ConversationState.SELECT_ASADO,
        ConversationState.SELECT_BROASTER,
        ConversationState.SELECT_BEBIDA,
        ConversationState.SELECT_ADICIONAL,
        ConversationState.SELECT_ESPECIAL,
    }:
        return "fallback_natural_language"
    return "select_product"


def route_after_product_selection(state: ConversationGraphState) -> str:
    if _value(state, "intent") in {
        ConversationIntent.PRODUCTO_INEXISTENTE,
        ConversationIntent.PRODUCTO_RESTRINGIDO,
    }:
        return "send_telegram_response"
    return "validate_product_availability"


def route_after_product_availability(state: ConversationGraphState) -> str:
    if _value(state, "intent") in {
        ConversationIntent.PRODUCTO_INEXISTENTE,
        ConversationIntent.PRODUCTO_RESTRINGIDO,
    }:
        return "send_telegram_response"
    return "ask_quantity"


def route_after_customer_validation(state: ConversationGraphState) -> str:
    if _value(state, "errors"):
        return "send_telegram_response"
    return "calculate_delivery"
