"""Administrative order operations used by the restaurant panel.

The bot-facing order domain remains focused on customer checkout. This service
adds the restaurant workflow: incoming, accepted/printed and rejected orders.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.modules.orders.domain.enums import OrderStatus
from app.modules.orders.infrastructure.models import OrderORM


INCOMING_ORDER_STATUSES = {
    OrderStatus.PENDING.value,
    OrderStatus.CONFIRMED.value,
}
ACCEPTED_ORDER_STATUSES = {
    OrderStatus.ACCEPTED.value,
    OrderStatus.PRINTED.value,
}
REJECTED_ORDER_STATUSES = {
    OrderStatus.REJECTED.value,
}


class AdminOrderStateError(ValueError):
    """Raised when an admin action is not allowed for the current order state."""


def mark_order_accepted(order: OrderORM) -> None:
    if order.status == OrderStatus.REJECTED.value:
        raise AdminOrderStateError("Rejected orders cannot be accepted.")
    now = datetime.now(timezone.utc)
    order.status = OrderStatus.ACCEPTED.value
    order.accepted_at = order.accepted_at or now


def mark_order_rejected(order: OrderORM, reason: str | None = None) -> None:
    if order.status == OrderStatus.PRINTED.value:
        raise AdminOrderStateError("Printed orders cannot be rejected.")
    now = datetime.now(timezone.utc)
    order.status = OrderStatus.REJECTED.value
    order.rejected_at = order.rejected_at or now
    order.rejection_reason = reason.strip() if reason and reason.strip() else None


def mark_order_printed(order: OrderORM) -> None:
    if order.status == OrderStatus.REJECTED.value:
        raise AdminOrderStateError("Rejected orders cannot be printed.")
    now = datetime.now(timezone.utc)
    order.status = OrderStatus.PRINTED.value
    order.accepted_at = order.accepted_at or now
    order.printed_at = now

