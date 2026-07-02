"""Conversation orchestration code. It should coordinate state transitions and delegate business work to use cases/services."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.modules.conversations.domain.conversation_state import ConversationState
from app.modules.conversations.domain.intent import ConversationIntent


class CartLineState(BaseModel):
    product_code: str
    product_name: str
    unit_price_cop: int
    quantity: int
    subtotal_cop: int


class CustomerDataState(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    neighborhood: Optional[str] = None
    payment_method: Optional[str] = None
    observations: Optional[str] = None


class ConversationGraphState(BaseModel):
    chat_id: int
    raw_text: str
    normalized_text: str = ""
    first_name: Optional[str] = None
    username: Optional[str] = None
    message_type: str = "text"
    current_step: ConversationState = ConversationState.MAIN_MENU
    intent: Optional[ConversationIntent] = None
    selected_product_code: Optional[str] = None
    selected_product_name: Optional[str] = None
    selected_unit_price_cop: Optional[int] = None
    quantity: Optional[int] = None
    cart: List[CartLineState] = Field(default_factory=list)
    customer: CustomerDataState = Field(default_factory=CustomerDataState)
    delivery_price_cop: Optional[int] = None
    subtotal_cop: int = 0
    total_cop: int = 0
    order_number: Optional[str] = None
    response_text: str = ""
    errors: List[str] = Field(default_factory=list)
    should_send_response: bool = True
    query_type: Optional[str] = None
    query_value: Optional[str] = None
