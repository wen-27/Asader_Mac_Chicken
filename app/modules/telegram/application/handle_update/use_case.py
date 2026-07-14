"""Telegram update application flow.

This use case is the boundary between Telegram and the bot conversation. It
persists inbound/outbound messages, prevents duplicate update processing and
serializes messages per chat so two rapid user messages cannot corrupt state.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from time import perf_counter

from app.modules.conversations.application.outbound_messages import split_outbound_messages
from app.modules.conversations.application.ports import ConversationMessageHandler
from app.modules.telegram.application.ports import TelegramClient, TelegramMessageRepository
from app.modules.telegram.domain.telegram_message import TelegramMessage
from app.shared.application.redis_ports import RedisIdempotencyPort, RedisLockPort
from app.shared.domain.value_object import ChatId
from app.shared.utils.text_normalizer import normalize_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramInboundMessage:
    update_id: int
    message_id: int
    chat_id: int
    text: str
    first_name: str | None
    username: str | None
    message_type: str


@dataclass(frozen=True)
class TelegramUpdateResult:
    processed: bool
    duplicated: bool
    response_text: str | None = None


class HandleTelegramUpdateUseCase:
    def __init__(
        self,
        messages: TelegramMessageRepository,
        telegram_client: TelegramClient,
        conversation_handler: ConversationMessageHandler,
        idempotency: RedisIdempotencyPort | None = None,
        locks: RedisLockPort | None = None,
        idempotency_ttl_seconds: int = 86_400,
        processing_ttl_seconds: int = 120,
        lock_ttl_seconds: int = 30,
    ) -> None:
        self._messages = messages
        self._telegram_client = telegram_client
        self._conversation_handler = conversation_handler
        self._idempotency = idempotency
        self._locks = locks
        self._idempotency_ttl_seconds = idempotency_ttl_seconds
        self._processing_ttl_seconds = processing_ttl_seconds
        self._lock_ttl_seconds = lock_ttl_seconds

    async def execute(self, inbound: TelegramInboundMessage) -> TelegramUpdateResult:
        idempotency_key = f"telegram:update:{inbound.update_id}:message:{inbound.message_id}"
        if self._idempotency is not None:
            # Telegram retries webhooks. Redis blocks duplicates quickly, while
            # PostgreSQL remains the durable second line of defense below.
            if await self._idempotency.is_processed(idempotency_key):
                return TelegramUpdateResult(processed=False, duplicated=True)
            if not await self._idempotency.mark_processing(
                idempotency_key,
                self._processing_ttl_seconds,
            ):
                return TelegramUpdateResult(processed=False, duplicated=True)

        existing = await self._messages.get_inbound_by_update_id(inbound.update_id)
        if existing is not None:
            if self._idempotency is not None:
                await self._idempotency.mark_processed(
                    idempotency_key,
                    self._idempotency_ttl_seconds,
                )
            return TelegramUpdateResult(processed=False, duplicated=True)

        chat_id = ChatId(inbound.chat_id)
        lock_key = f"telegram:chat-lock:{chat_id.value}"
        lock_token = None
        if self._locks is not None:
            # One chat must be processed sequentially because the conversation
            # session carries current_step, selected product and cart JSON.
            lock_token = await self._locks.acquire(lock_key, self._lock_ttl_seconds)
            if lock_token is None:
                return TelegramUpdateResult(processed=False, duplicated=True)

        try:
            return await self._process(inbound, chat_id, idempotency_key)
        finally:
            if self._locks is not None and lock_token is not None:
                await self._locks.release(lock_key, lock_token)

    async def _process(
        self,
        inbound: TelegramInboundMessage,
        chat_id: ChatId,
        idempotency_key: str,
    ) -> TelegramUpdateResult:
        started_at = perf_counter()
        normalized_text = normalize_text(inbound.text)
        inbound_message = TelegramMessage(
            chat_id=chat_id,
            message_id=inbound.message_id,
            update_id=inbound.update_id,
            text_raw=inbound.text,
            text_normalized=normalized_text,
        )
        await self._messages.add(inbound_message, direction="inbound")

        # Pass the raw text to the conversation. Normalized text removes line
        # breaks, and checkout data often arrives as several human-written lines.
        conversation_started_at = perf_counter()
        response_text = await self._conversation_handler.handle(inbound.text, chat_id)
        response_texts = split_outbound_messages(response_text)
        conversation_ms = round((perf_counter() - conversation_started_at) * 1000, 2)
        send_started_at = perf_counter()
        sent_messages = [
            await self._telegram_client.send_text_message(chat_id, outbound_text)
            for outbound_text in response_texts
        ]
        send_ms = round((perf_counter() - send_started_at) * 1000, 2)
        if self._idempotency is not None:
            # Once WhatsApp/Telegram accepted the outbound message, mark the
            # inbound update as processed before any secondary persistence can
            # fail. Otherwise the platform may retry the webhook and the user
            # can receive the same bot reply twice.
            await self._idempotency.mark_processed(
                idempotency_key,
                self._idempotency_ttl_seconds,
            )
        save_started_at = perf_counter()
        for sent_message in sent_messages:
            await self._messages.add(sent_message, direction="outbound")
        save_ms = round((perf_counter() - save_started_at) * 1000, 2)
        total_ms = round((perf_counter() - started_at) * 1000, 2)
        logger.info(
            "telegram update timings chat_id=%s update_id=%s conversation_ms=%s send_ms=%s outbound_save_ms=%s total_ms=%s",
            chat_id.value,
            inbound.update_id,
            conversation_ms,
            send_ms,
            save_ms,
            total_ms,
        )

        return TelegramUpdateResult(
            processed=True,
            duplicated=False,
            response_text=response_text,
        )
