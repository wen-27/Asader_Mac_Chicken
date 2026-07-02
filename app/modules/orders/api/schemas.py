"""Pydantic schemas for administrative order/factura endpoints.

These DTOs intentionally use frontend-friendly camelCase keys while the ORM
keeps the existing snake_case database columns untouched.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AdminOrderStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    PRINTED = "PRINTED"


class AdminCustomerSchema(BaseModel):
    fullName: str
    phone: str
    address: str
    neighborhood: str


class AdminOrderItemSchema(BaseModel):
    id: str
    productCode: str | None = None
    productName: str
    quantity: int
    unitPrice: int
    subtotal: int


class AdminOrderSchema(BaseModel):
    id: str
    orderNumber: str
    invoiceNumber: str | None = None
    status: AdminOrderStatus
    customer: AdminCustomerSchema
    paymentMethod: str
    observations: str | None = None
    items: list[AdminOrderItemSchema]
    subtotal: int
    deliveryFee: int
    total: int
    createdAt: datetime
    acceptedAt: datetime | None = None
    rejectedAt: datetime | None = None
    printedAt: datetime | None = None
    rejectionReason: str | None = None


class RejectOrderRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)

