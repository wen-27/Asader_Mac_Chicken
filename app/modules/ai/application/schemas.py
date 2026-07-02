"""Pydantic DTOs for API/AI boundaries. They validate transport data without leaking framework concerns into domain code."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ParsedOrderItem(BaseModel):
    code: str
    quantity: int = Field(default=1, ge=1)


class ParsedCustomer(BaseModel):
    name: str = ""
    phone: str = ""
    address: str = ""
    neighborhood: str = ""
    paymentMethod: str = ""


class NaturalLanguageOrderParse(BaseModel):
    intent: str = "order_items"
    items: list[ParsedOrderItem] = Field(default_factory=list)
    customer: ParsedCustomer = Field(default_factory=ParsedCustomer)
    wantsCheckout: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)

