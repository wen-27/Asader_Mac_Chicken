"""Conversation orchestration code. It should coordinate state transitions and delegate business work to use cases/services."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.cart.domain.cart_item import CartItem
from app.modules.conversations.domain.conversation_state import ConversationState
from app.shared.domain.money import MoneyCOP
from app.shared.domain.value_object import ChatId, ProductCode


@dataclass()
class TelegramSession:
    chat_id: ChatId
    current_step: ConversationState = ConversationState.MAIN_MENU
    selected_product_code: ProductCode | None = None
    selected_chicken_part: str | None = None
    cart: list[CartItem] = field(default_factory=list)
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_address: str | None = None
    customer_neighborhood: str | None = None
    payment_method: str | None = None
    observations: str | None = None
    fulfillment_type: str = "DELIVERY"

    @property
    def phone(self) -> str | None:
        return self.customer_phone

    @phone.setter
    def phone(self, value: str | None) -> None:
        self.customer_phone = value

    @property
    def address(self) -> str | None:
        return self.customer_address

    @address.setter
    def address(self, value: str | None) -> None:
        self.customer_address = value

    @property
    def neighborhood(self) -> str | None:
        return self.customer_neighborhood

    @neighborhood.setter
    def neighborhood(self, value: str | None) -> None:
        self.customer_neighborhood = value

    def move_to(self, step: ConversationState) -> None:
        self.current_step = step

    def select_product(self, product_code: ProductCode) -> None:
        self.selected_product_code = product_code
        self.selected_chicken_part = None
        self.current_step = ConversationState.ASK_QUANTITY

    def clear_selected_product(self) -> None:
        self.selected_product_code = None
        self.selected_chicken_part = None

    def add_cart_item(self, item: CartItem) -> None:
        self.cart.append(item)
        self.current_step = ConversationState.POST_ADD

    def empty_cart(self) -> None:
        self.cart.clear()

    def update_customer_data(
        self,
        customer_name: str | None = None,
        phone: str | None = None,
        address: str | None = None,
        neighborhood: str | None = None,
        payment_method: str | None = None,
        observations: str | None = None,
        fulfillment_type: str | None = None,
    ) -> None:
        self.customer_name = customer_name
        self.phone = phone
        self.address = address
        self.neighborhood = neighborhood
        self.payment_method = payment_method
        self.observations = observations
        if fulfillment_type is not None:
            self.fulfillment_type = fulfillment_type

    def clear_customer_data(self) -> None:
        self.update_customer_data(fulfillment_type="DELIVERY")

    def remove_last_cart_item(self) -> CartItem | None:
        if not self.cart:
            return None
        return self.cart.pop()

    @property
    def cart_total(self) -> MoneyCOP:
        total = MoneyCOP(0)
        for item in self.cart:
            total += item.subtotal
        return total
