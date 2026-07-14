"""Mapping helpers between pure domain objects and infrastructure/ORM records."""

from __future__ import annotations

from app.modules.cart.domain.cart_item import CartItem
from app.modules.conversations.domain.conversation_state import ConversationState
from app.modules.conversations.domain.telegram_session import TelegramSession
from app.modules.conversations.infrastructure.models import TelegramSessionORM
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import ChatId, ProductCode, ProductName


PENDING_ORDER_MARKER = "__pending_order__"


def cart_item_to_json(item: CartItem) -> dict[str, object]:
    return {
        "product_code": item.product_code.value,
        "product_name": item.product_name.value,
        "unit_price_cop": item.unit_price.amount,
        "quantity": item.quantity,
        "subtotal_cop": item.subtotal.amount,
    }


def cart_item_from_json(data: dict[str, object]) -> CartItem:
    return CartItem(
        product_code=ProductCode(str(data["product_code"])),
        product_name=ProductName(str(data["product_name"])),
        unit_price=MoneyCOP(int(data["unit_price_cop"])),
        quantity=int(data["quantity"]),
    )


def session_to_orm(session: TelegramSession) -> TelegramSessionORM:
    return TelegramSessionORM(
        chat_id=session.chat_id.value,
        current_step=session.current_step.value,
        selected_product_code=(
            session.selected_product_code.value if session.selected_product_code else None
        ),
        selected_chicken_part=session.selected_chicken_part,
        cart_json=_cart_json_to_storage(session),
        customer_name=session.customer_name,
        phone=session.customer_phone,
        address=session.customer_address,
        neighborhood=session.customer_neighborhood,
        payment_method=session.payment_method,
        observations=session.observations,
        fulfillment_type=session.fulfillment_type,
    )


def update_session_orm(row: TelegramSessionORM, session: TelegramSession) -> TelegramSessionORM:
    row.current_step = session.current_step.value
    row.selected_product_code = (
        session.selected_product_code.value if session.selected_product_code else None
    )
    row.selected_chicken_part = session.selected_chicken_part
    row.cart_json = _cart_json_to_storage(session)
    row.customer_name = session.customer_name
    row.phone = session.customer_phone
    row.address = session.customer_address
    row.neighborhood = session.customer_neighborhood
    row.payment_method = session.payment_method
    row.observations = session.observations
    row.fulfillment_type = session.fulfillment_type
    return row


def session_from_orm(row: TelegramSessionORM) -> TelegramSession:
    cart, pending_order_json = _cart_json_from_storage(row.cart_json)
    return TelegramSession(
        chat_id=ChatId(row.chat_id),
        current_step=ConversationState(row.current_step),
        selected_product_code=(
            ProductCode(row.selected_product_code) if row.selected_product_code else None
        ),
        selected_chicken_part=row.selected_chicken_part,
        cart=cart,
        pending_order_json=pending_order_json,
        customer_name=row.customer_name,
        customer_phone=row.phone,
        customer_address=row.address,
        customer_neighborhood=row.neighborhood,
        payment_method=row.payment_method,
        observations=row.observations,
        fulfillment_type=row.fulfillment_type or "DELIVERY",
    )


def _cart_json_to_storage(session: TelegramSession) -> list[dict[str, object]]:
    items = [cart_item_to_json(item) for item in session.cart]
    if session.pending_order_json:
        items.append({PENDING_ORDER_MARKER: True, "payload": session.pending_order_json})
    return items


def _cart_json_from_storage(values: list[dict[str, object]]) -> tuple[list[CartItem], dict[str, object] | None]:
    cart: list[CartItem] = []
    pending_order_json: dict[str, object] | None = None
    for value in values or []:
        if value.get(PENDING_ORDER_MARKER):
            payload = value.get("payload")
            if isinstance(payload, dict):
                pending_order_json = payload
            continue
        cart.append(cart_item_from_json(value))
    return cart, pending_order_json
