"""Pydantic DTOs for WhatsApp Cloud API webhook payloads."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from pydantic import BaseModel, Field


class WhatsAppTextSchema(BaseModel):
    body: str | None = None


class WhatsAppButtonReplySchema(BaseModel):
    id: str | None = None
    title: str | None = None


class WhatsAppInteractiveSchema(BaseModel):
    type: str | None = None
    button_reply: WhatsAppButtonReplySchema | None = None


class WhatsAppProfileSchema(BaseModel):
    name: str | None = None


class WhatsAppContactSchema(BaseModel):
    profile: WhatsAppProfileSchema | None = None
    wa_id: str | None = None


class WhatsAppMessageSchema(BaseModel):
    id: str
    from_phone: str = Field(alias="from")
    timestamp: str | None = None
    type: str
    text: WhatsAppTextSchema | None = None
    interactive: WhatsAppInteractiveSchema | None = None

    @property
    def body(self) -> str:
        if self.type == "text" and self.text is not None:
            return self.text.body or ""
        if self.type == "interactive" and self.interactive is not None:
            button = self.interactive.button_reply
            if button is None:
                return ""
            if button.id == "confirm_order_yes":
                return "si"
            if button.id == "confirm_order_no":
                return "no"
            return button.title or ""
        return ""


class WhatsAppMetadataSchema(BaseModel):
    phone_number_id: str | None = None
    display_phone_number: str | None = None


class WhatsAppValueSchema(BaseModel):
    messaging_product: str | None = None
    metadata: WhatsAppMetadataSchema | None = None
    contacts: list[WhatsAppContactSchema] | None = None
    messages: list[WhatsAppMessageSchema] | None = None


class WhatsAppChangeSchema(BaseModel):
    field: str | None = None
    value: WhatsAppValueSchema


class WhatsAppEntrySchema(BaseModel):
    id: str | None = None
    changes: list[WhatsAppChangeSchema] = Field(default_factory=list)


@dataclass(frozen=True)
class WhatsAppInboundTextMessage:
    update_id: int
    message_id: int
    chat_id: int
    external_message_id: str
    phone: str
    text: str
    first_name: str | None


class WhatsAppWebhookPayload(BaseModel):
    object: str | None = None
    entry: list[WhatsAppEntrySchema] = Field(default_factory=list)

    def iter_text_messages(self) -> list[WhatsAppInboundTextMessage]:
        inbound_messages: list[WhatsAppInboundTextMessage] = []
        for entry in self.entry:
            for change in entry.changes:
                contacts_by_phone = {
                    contact.wa_id: contact.profile.name if contact.profile else None
                    for contact in change.value.contacts or []
                    if contact.wa_id and contact.profile and contact.profile.name
                }
                for message in change.value.messages or []:
                    if message.type not in {"text", "interactive"} or not message.body.strip():
                        continue
                    phone_digits = _digits_only(message.from_phone)
                    inbound_messages.append(
                        WhatsAppInboundTextMessage(
                            update_id=_stable_numeric_id(f"wa-update:{message.id}"),
                            message_id=_stable_numeric_id(f"wa-message:{message.id}"),
                            chat_id=int(phone_digits),
                            external_message_id=message.id,
                            phone=phone_digits,
                            text=message.body.strip(),
                            first_name=contacts_by_phone.get(message.from_phone)
                            or contacts_by_phone.get(phone_digits),
                        )
                    )
        return inbound_messages


def _digits_only(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return "1"
    return digits


def _stable_numeric_id(value: str) -> int:
    # PostgreSQL BigInt max is 9.22e18. 15 hex chars stay well below that.
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:15], 16)
