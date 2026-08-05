from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.modules.conversations.application.checkout_reminders import (
    _checkout_reminder_due,
    _has_cart_items,
    _mark_missing_customer_data_reminder_sent,
    _mark_checkout_reminder_sent,
    _missing_customer_data_reminder_due,
    _missing_customer_data_reminder_text,
    _missing_customer_fields,
)
from app.modules.conversations.infrastructure.mappers import PENDING_ORDER_MARKER
from app.modules.conversations.infrastructure.models import TelegramSessionORM


def test_checkout_reminder_detects_real_cart_items_ignoring_marker() -> None:
    assert _has_cart_items([{PENDING_ORDER_MARKER: True, "payload": {"kind": "checkout_confirmation_reminder"}}]) is False
    assert _has_cart_items([{"product_code": "ASADO_MEDIO", "quantity": 1}]) is True


def test_checkout_reminder_is_due_every_five_minutes() -> None:
    now = datetime.now(timezone.utc)
    cart_json = [{"product_code": "ASADO_MEDIO", "quantity": 1}]
    marked = _mark_checkout_reminder_sent(cart_json, now - timedelta(minutes=6))

    assert _checkout_reminder_due(cart_json, now) is True
    assert _checkout_reminder_due(marked, now - timedelta(minutes=5)) is True
    assert _checkout_reminder_due(_mark_checkout_reminder_sent(cart_json, now), now - timedelta(minutes=5)) is False


def test_missing_customer_data_reminder_is_due_every_three_minutes() -> None:
    now = datetime.now(timezone.utc)
    cart_json = [{"product_code": "ASADO_CUARTO", "quantity": 1}]
    marked = _mark_missing_customer_data_reminder_sent(cart_json, now - timedelta(minutes=4))

    assert _missing_customer_data_reminder_due(cart_json, now) is True
    assert _missing_customer_data_reminder_due(marked, now - timedelta(minutes=3)) is True
    assert _missing_customer_data_reminder_due(
        _mark_missing_customer_data_reminder_sent(cart_json, now),
        now - timedelta(minutes=3),
    ) is False


def test_missing_customer_data_reminder_detects_missing_exact_address() -> None:
    row = TelegramSessionORM(
        chat_id=123,
        current_step="ASK_CUSTOMER_DATA",
        cart_json=[{"product_code": "ASADO_CUARTO", "quantity": 1}],
        customer_name="Maria Márquez",
        phone="3209247968",
        address=None,
        neighborhood="Plaza la colmena de lagos 2",
        payment_method="Efectivo",
        fulfillment_type="DELIVERY",
    )

    assert _missing_customer_fields(row) == ["direccion"]
    assert "direccion" in _missing_customer_data_reminder_text(["direccion"])
