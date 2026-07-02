"""Conversation orchestration code. It should coordinate state transitions and delegate business work to use cases/services."""

from __future__ import annotations

from app.modules.conversations.application.graph_services import ConversationGraphServices
from app.modules.conversations.application.ports import ConversationMessageHandler
from app.modules.conversations.graph.graph import build_conversation_graph
from app.modules.conversations.graph.state import ConversationGraphState
from app.shared.domain.value_object import ChatId


class LangGraphConversationMessageHandler(ConversationMessageHandler):
    def __init__(self, services: ConversationGraphServices) -> None:
        self._graph = build_conversation_graph(services)

    async def handle(self, message_text: str, chat_id: ChatId) -> str:
        initial_state = ConversationGraphState(
            chat_id=chat_id.value,
            raw_text=message_text,
        )
        final_state = await self._graph.ainvoke(initial_state)
        if isinstance(final_state, ConversationGraphState):
            return final_state.response_text
        return str(final_state.get("response_text", ""))
