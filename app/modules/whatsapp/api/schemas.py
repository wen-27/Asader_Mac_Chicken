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


class WhatsAppImageSchema(BaseModel):
    id: str
    mime_type: str | None = None
    sha256: str | None = None
    caption: str | None = None


class WhatsAppCallSchema(BaseModel):
    id: str | None = None
    from_phone: str | None = Field(default=None, alias="from")
    timestamp: str | None = None
    status: str | None = None


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
    image: WhatsAppImageSchema | None = None

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
            if button.id and button.id.startswith("admin_preparing_yes"):
                return "Si"
            if button.id and button.id.startswith("admin_preparing_no"):
                return "No"
            return button.title or ""

    @property
    def button_reply_id(self) -> str | None:
        if self.type != "interactive" or self.interactive is None:
            return None
        button = self.interactive.button_reply
        if button is None:
            return None
        return button.id


class WhatsAppMetadataSchema(BaseModel):
    phone_number_id: str | None = None
    display_phone_number: str | None = None


class WhatsAppValueSchema(BaseModel):
    messaging_product: str | None = None
    metadata: WhatsAppMetadataSchema | None = None
    contacts: list[WhatsAppContactSchema] | None = None
    messages: list[WhatsAppMessageSchema] | None = None
    calls: list[WhatsAppCallSchema] | None = None


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
    button_reply_id: str | None
    sent_at_epoch: int | None
    first_name: str | None


@dataclass(frozen=True)
class WhatsAppInboundMediaMessage:
    update_id: int
    message_id: int
    chat_id: int
    external_message_id: str
    phone: str
    media_id: str
    media_type: str
    mime_type: str | None
    sha256: str | None
    caption: str | None
    sent_at_epoch: int | None
    first_name: str | None


@dataclass(frozen=True)
class WhatsAppInboundCallEvent:
    update_id: int
    message_id: int
    chat_id: int
    external_message_id: str
    phone: str
    status: str | None
    sent_at_epoch: int | None
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
                            button_reply_id=message.button_reply_id,
                            sent_at_epoch=_parse_epoch(message.timestamp),
                            first_name=contacts_by_phone.get(message.from_phone)
                            or contacts_by_phone.get(phone_digits),
                        )
                    )
        return inbound_messages

    def iter_media_messages(self) -> list[WhatsAppInboundMediaMessage]:
        inbound_messages: list[WhatsAppInboundMediaMessage] = []
        for entry in self.entry:
            for change in entry.changes:
                contacts_by_phone = {
                    contact.wa_id: contact.profile.name if contact.profile else None
                    for contact in change.value.contacts or []
                    if contact.wa_id and contact.profile and contact.profile.name
                }
                for message in change.value.messages or []:
                    if message.type != "image" or message.image is None:
                        continue
                    phone_digits = _digits_only(message.from_phone)
                    inbound_messages.append(
                        WhatsAppInboundMediaMessage(
                            update_id=_stable_numeric_id(f"wa-update:{message.id}"),
                            message_id=_stable_numeric_id(f"wa-message:{message.id}"),
                            chat_id=int(phone_digits),
                            external_message_id=message.id,
                            phone=phone_digits,
                            media_id=message.image.id,
                            media_type="image",
                            mime_type=message.image.mime_type,
                            sha256=message.image.sha256,
                            caption=(message.image.caption or "").strip() or None,
                            sent_at_epoch=_parse_epoch(message.timestamp),
                            first_name=contacts_by_phone.get(message.from_phone)
                            or contacts_by_phone.get(phone_digits),
                        )
                    )
        return inbound_messages

    def iter_call_events(self) -> list[WhatsAppInboundCallEvent]:
        inbound_calls: list[WhatsAppInboundCallEvent] = []
        for entry in self.entry:
            for change in entry.changes:
                contacts_by_phone = {
                    contact.wa_id: contact.profile.name if contact.profile else None
                    for contact in change.value.contacts or []
                    if contact.wa_id and contact.profile and contact.profile.name
                }
                for call in change.value.calls or []:
                    if not call.from_phone:
                        continue
                    phone_digits = _digits_only(call.from_phone)
                    external_id = call.id or f"call:{phone_digits}:{call.timestamp or ''}:{call.status or ''}"
                    inbound_calls.append(
                        WhatsAppInboundCallEvent(
                            update_id=_stable_numeric_id(f"wa-call-update:{external_id}"),
                            message_id=_stable_numeric_id(f"wa-call-message:{external_id}"),
                            chat_id=int(phone_digits),
                            external_message_id=external_id,
                            phone=phone_digits,
                            status=call.status,
                            sent_at_epoch=_parse_epoch(call.timestamp),
                            first_name=contacts_by_phone.get(call.from_phone)
                            or contacts_by_phone.get(phone_digits),
                        )
                    )
        return inbound_calls


def _digits_only(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return "1"
    return digits


def _stable_numeric_id(value: str) -> int:
    # PostgreSQL BigInt max is 9.22e18. 15 hex chars stay well below that.
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:15], 16)


def _parse_epoch(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
