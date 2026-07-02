"""Conversation orchestration code. It should coordinate state transitions and delegate business work to use cases/services."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langgraph.graph import END, StateGraph

from app.modules.conversations.application.graph_services import ConversationGraphServices
from app.modules.conversations.graph import nodes
from app.modules.conversations.graph.router import (
    route_after_customer_validation,
    route_after_intent,
    route_after_product_availability,
    route_after_product_selection,
)
from app.modules.conversations.graph.state import ConversationGraphState


NodeFn = Callable[[ConversationGraphState, ConversationGraphServices], Awaitable[ConversationGraphState]]


def _bind(
    fn: NodeFn,
    services: ConversationGraphServices,
) -> Callable[[ConversationGraphState], Awaitable[ConversationGraphState]]:
    async def wrapped(state: ConversationGraphState) -> ConversationGraphState:
        return await fn(state, services)

    return wrapped


def build_conversation_graph(services: ConversationGraphServices):
    graph = StateGraph(ConversationGraphState)

    graph.add_node("receive_message", _bind(nodes.receive_message, services))
    graph.add_node("normalize_message", _bind(nodes.normalize_message, services))
    graph.add_node("load_or_create_session", _bind(nodes.load_or_create_session, services))
    graph.add_node("detect_intent", _bind(nodes.detect_intent, services))
    graph.add_node("route_intent", _bind(nodes.route_intent, services))
    graph.add_node("show_main_menu", _bind(nodes.show_main_menu, services))
    graph.add_node("show_product_categories", _bind(nodes.show_product_categories, services))
    graph.add_node("show_asado_menu", _bind(nodes.show_asado_menu, services))
    graph.add_node("show_broaster_menu", _bind(nodes.show_broaster_menu, services))
    graph.add_node("show_drinks_menu", _bind(nodes.show_drinks_menu, services))
    graph.add_node("show_addons_menu", _bind(nodes.show_addons_menu, services))
    graph.add_node("show_specials_menu", _bind(nodes.show_specials_menu, services))
    graph.add_node("select_product", _bind(nodes.select_product, services))
    graph.add_node("validate_product_availability", _bind(nodes.validate_product_availability, services))
    graph.add_node("ask_quantity", _bind(nodes.ask_quantity, services))
    graph.add_node("add_to_cart", _bind(nodes.add_to_cart, services))
    graph.add_node("show_cart", _bind(nodes.show_cart, services))
    graph.add_node("clear_cart", _bind(nodes.clear_cart, services))
    graph.add_node("remove_last_item", _bind(nodes.remove_last_item, services))
    graph.add_node("prepare_checkout_summary", _bind(nodes.prepare_checkout_summary, services))
    graph.add_node("ask_customer_data", _bind(nodes.ask_customer_data, services))
    graph.add_node("extract_customer_data", _bind(nodes.extract_customer_data, services))
    graph.add_node("validate_customer_data", _bind(nodes.validate_customer_data, services))
    graph.add_node("calculate_delivery", _bind(nodes.calculate_delivery, services))
    graph.add_node("create_order", _bind(nodes.create_order, services))
    graph.add_node("confirm_order", _bind(nodes.confirm_order, services))
    graph.add_node("cancel_order", _bind(nodes.cancel_order, services))
    graph.add_node("send_telegram_response", _bind(nodes.send_telegram_response, services))
    graph.add_node("fallback_natural_language", _bind(nodes.fallback_natural_language, services))
    graph.add_node("show_schedules", _bind(nodes.show_schedules, services))
    graph.add_node("go_back", _bind(nodes.go_back, services))
    graph.add_node("answer_query", _bind(nodes.answer_query, services))

    graph.set_entry_point("receive_message")
    graph.add_edge("receive_message", "normalize_message")
    graph.add_edge("normalize_message", "load_or_create_session")
    graph.add_edge("load_or_create_session", "detect_intent")
    graph.add_edge("detect_intent", "route_intent")
    graph.add_conditional_edges("route_intent", route_after_intent)
    graph.add_conditional_edges("select_product", route_after_product_selection)
    graph.add_conditional_edges("validate_product_availability", route_after_product_availability)
    graph.add_edge("ask_quantity", "send_telegram_response")
    graph.add_edge("add_to_cart", "send_telegram_response")
    graph.add_edge("show_main_menu", "send_telegram_response")
    graph.add_edge("show_product_categories", "send_telegram_response")
    graph.add_edge("show_asado_menu", "send_telegram_response")
    graph.add_edge("show_broaster_menu", "send_telegram_response")
    graph.add_edge("show_drinks_menu", "send_telegram_response")
    graph.add_edge("show_addons_menu", "send_telegram_response")
    graph.add_edge("show_specials_menu", "send_telegram_response")
    graph.add_edge("show_cart", "send_telegram_response")
    graph.add_edge("clear_cart", "send_telegram_response")
    graph.add_edge("remove_last_item", "send_telegram_response")
    graph.add_edge("prepare_checkout_summary", "send_telegram_response")
    graph.add_edge("ask_customer_data", "send_telegram_response")
    graph.add_edge("extract_customer_data", "validate_customer_data")
    graph.add_conditional_edges("validate_customer_data", route_after_customer_validation)
    graph.add_edge("calculate_delivery", "create_order")
    graph.add_edge("create_order", "send_telegram_response")
    graph.add_edge("confirm_order", "send_telegram_response")
    graph.add_edge("cancel_order", "send_telegram_response")
    graph.add_edge("show_schedules", "send_telegram_response")
    graph.add_edge("go_back", "send_telegram_response")
    graph.add_edge("answer_query", "send_telegram_response")
    graph.add_edge("fallback_natural_language", "send_telegram_response")
    graph.add_edge("send_telegram_response", END)

    return graph.compile()
