"""Automated test module. It documents expected behavior and protects production bot flows from regressions."""

from __future__ import annotations

from app.modules.telegram.api.schemas import TelegramUpdateSchema


def test_telegram_update_extracts_chat_id() -> None:
    update = TelegramUpdateSchema.model_validate(
        {
            "update_id": 123,
            "message": {
                "message_id": 456,
                "chat": {"id": 789, "first_name": "Ana", "username": "ana"},
                "from": {"id": 1, "first_name": "Ana", "username": "ana_user"},
                "text": "Menu",
            },
        }
    )

    assert update.update_id == 123
    assert update.message_id == 456
    assert update.chat_id == 789
    assert update.text == "Menu"
    assert update.first_name == "Ana"
    assert update.username == "ana_user"
    assert update.message_type == "text"

