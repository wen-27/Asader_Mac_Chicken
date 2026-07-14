"""Helpers for bot replies that must be sent as separate chat bubbles."""

from typing import Optional

BOT_MESSAGE_SEPARATOR = "\n\n[[BOT_NEXT_MESSAGE]]\n\n"


def join_outbound_messages(messages: list[str]) -> str:
    return BOT_MESSAGE_SEPARATOR.join(message.strip() for message in messages if message and message.strip())


def split_outbound_messages(response_text: Optional[str]) -> list[str]:
    if not response_text:
        return []
    return [part.strip() for part in response_text.split(BOT_MESSAGE_SEPARATOR) if part.strip()]
