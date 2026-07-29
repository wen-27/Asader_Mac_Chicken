"""Conversation orchestration code.

It should coordinate state transitions and delegate business work to use
cases/services.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

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


class ConversationGraphRunner:
    def __init__(self, services: ConversationGraphServices) -> None:
        self._services = services

    async def ainvoke(self, state: ConversationGraphState | dict) -> dict:
        graph_state = self._coerce_state(state)
        graph_state = await nodes.receive_message(graph_state, self._services)
        graph_state = await nodes.normalize_message(graph_state, self._services)
        graph_state = await nodes.load_or_create_session(graph_state, self._services)
        graph_state = await nodes.detect_intent(graph_state, self._services)

        next_node = route_after_intent(graph_state)
        graph_state = await self._run_node(next_node, graph_state)
        graph_state = await self._run_until_response(next_node, graph_state)
        return graph_state.model_dump()

    def _coerce_state(self, state: ConversationGraphState | dict) -> ConversationGraphState:
        if isinstance(state, ConversationGraphState):
            return state
        return ConversationGraphState.model_validate(state)

    async def _run_until_response(
        self,
        previous_node: str,
        state: ConversationGraphState,
    ) -> ConversationGraphState:
        if previous_node == "select_product":
            next_node = route_after_product_selection(state)
            state = await self._run_node(next_node, state)
            previous_node = next_node

        if previous_node == "validate_product_availability":
            next_node = route_after_product_availability(state)
            state = await self._run_node(next_node, state)
            previous_node = next_node

        if previous_node == "extract_customer_data":
            state = await nodes.validate_customer_data(state, self._services)
            next_node = route_after_customer_validation(state)
            state = await self._run_node(next_node, state)
            previous_node = next_node

        if previous_node == "calculate_delivery":
            if not state.errors and not state.response_text:
                state = await nodes.create_order(state, self._services)
                previous_node = "create_order"

        if previous_node != "send_telegram_response":
            state = await nodes.send_telegram_response(state, self._services)
        return state

    async def _run_node(
        self,
        name: str,
        state: ConversationGraphState,
    ) -> ConversationGraphState:
        node = _NODE_REGISTRY.get(name)
        if node is None:
            return await nodes.fallback_natural_language(state, self._services)
        return await node(state, self._services)


_NODE_REGISTRY: dict[str, NodeFn] = {
    "show_main_menu": nodes.show_main_menu,
    "show_product_categories": nodes.show_product_categories,
    "show_asado_menu": nodes.show_asado_menu,
    "show_broaster_menu": nodes.show_broaster_menu,
    "show_drinks_menu": nodes.show_drinks_menu,
    "show_addons_menu": nodes.show_addons_menu,
    "show_specials_menu": nodes.show_specials_menu,
    "select_product": nodes.select_product,
    "validate_product_availability": nodes.validate_product_availability,
    "ask_quantity": nodes.ask_quantity,
    "add_to_cart": nodes.add_to_cart,
    "add_half_combo_to_cart": nodes.add_half_combo_to_cart,
    "continue_without_soup": nodes.continue_without_soup,
    "show_cart": nodes.show_cart,
    "clear_cart": nodes.clear_cart,
    "remove_last_item": nodes.remove_last_item,
    "prepare_checkout_summary": nodes.prepare_checkout_summary,
    "ask_customer_data": nodes.ask_customer_data,
    "extract_customer_data": nodes.extract_customer_data,
    "calculate_delivery": nodes.calculate_delivery,
    "create_order": nodes.create_order,
    "confirm_order": nodes.confirm_order,
    "cancel_order": nodes.cancel_order,
    "send_telegram_response": nodes.send_telegram_response,
    "fallback_natural_language": nodes.fallback_natural_language,
    "show_schedules": nodes.show_schedules,
    "show_outside_business_hours": nodes.show_outside_business_hours,
    "start_delivery_order": nodes.start_delivery_order,
    "go_back": nodes.go_back,
    "answer_query": nodes.answer_query,
}

def build_conversation_graph(services: ConversationGraphServices) -> ConversationGraphRunner:
    return ConversationGraphRunner(services)
