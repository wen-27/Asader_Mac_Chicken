"""Regression tests for conversation session mapping."""

from __future__ import annotations

from app.modules.conversations.domain.telegram_session import TelegramSession
from app.modules.conversations.infrastructure.mappers import (
    session_from_orm,
    session_to_orm,
)
from app.shared.domain.value_object import ChatId, ProductCode


def test_pending_order_is_stored_inside_existing_cart_json_field() -> None:
    session = TelegramSession(
        chat_id=ChatId(123),
        selected_product_code=ProductCode("ASADO_CUARTO"),
        pending_order_json={
            "items": [{"code": "ASADO_CUARTO", "quantity": 4}],
            "current_index": 0,
            "allocations": [{"part": "Pierna", "quantity": 2}],
        },
    )

    row = session_to_orm(session)

    assert not hasattr(row, "pending_order_json")
    assert row.selected_chicken_part is None
    assert row.cart_json[-1]["__pending_order__"] is True

    restored = session_from_orm(row)

    assert restored.selected_chicken_part is None
    assert restored.pending_order_json == session.pending_order_json
