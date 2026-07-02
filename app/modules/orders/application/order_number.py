"""Order-number generator logic kept separate so numbering can evolve without touching persistence."""

from __future__ import annotations

from datetime import datetime, timezone


def generate_order_number(chat_id: int) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"MC-{chat_id}-{timestamp}"

