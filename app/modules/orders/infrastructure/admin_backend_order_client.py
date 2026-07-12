"""Internal HTTP client that syncs confirmed bot orders into the admin backend."""

from __future__ import annotations

from dataclasses import dataclass
import logging

import httpx

from app.config.settings import Settings
from app.modules.orders.domain.order import Order

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdminOrderCustomerPayload:
    full_name: str
    phone: str
    address: str


@dataclass(frozen=True)
class AdminOrderItemPayload:
    product_code: str
    product_name: str
    quantity: int
    unit_price_cop: int
    notes: str | None = None


@dataclass(frozen=True)
class AdminOrderPayload:
    external_bot_id: str
    chat_id: str
    customer: AdminOrderCustomerPayload
    payment_method: str
    observations: str | None
    delivery_fee_cop: int
    items: list[AdminOrderItemPayload]


class AdminBackendOrderClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.admin_backend_base_url.rstrip("/")
        self._api_key = settings.internal_api_key
        self._enabled = settings.admin_backend_sync_enabled

    async def sync_confirmed_order(self, order: Order, chat_id: int) -> None:
        payload = AdminOrderPayload(
            external_bot_id=str(order.order_id.value),
            chat_id=str(chat_id),
            customer=AdminOrderCustomerPayload(
                full_name=order.customer.name.value,
                phone=order.customer.phone.value,
                address=f"{order.customer.address.value} - {order.customer.neighborhood.value}",
            ),
            payment_method=str(order.payment_method.value),
            observations=order.customer.observations or order.notes or None,
            delivery_fee_cop=order.delivery_zone.delivery_price.amount,
            items=[
                AdminOrderItemPayload(
                    product_code=item.product_code.value,
                    product_name=item.product_name.value,
                    quantity=item.quantity,
                    unit_price_cop=item.unit_price_snapshot.amount,
                )
                for item in order.items
            ],
        )
        await self.sync_order_payload(payload)

    async def sync_order_payload(self, payload: AdminOrderPayload) -> None:
        if not self._enabled:
            logger.info("admin backend order sync is disabled; skipping external sync")
            return
        if not self._api_key:
            logger.warning("internal api key is not configured; skipping admin backend order sync")
            return

        request_body = {
            "externalBotId": payload.external_bot_id,
            "chatId": payload.chat_id,
            "customer": {
                "fullName": payload.customer.full_name,
                "phone": payload.customer.phone,
                "address": payload.customer.address,
            },
            "paymentMethod": payload.payment_method,
            "deliveryFeeCop": payload.delivery_fee_cop,
            "items": [
                {
                    "productCode": item.product_code,
                    "productName": item.product_name,
                    "quantity": item.quantity,
                    "unitPriceCop": item.unit_price_cop,
                }
                for item in payload.items
            ],
        }
        if payload.observations:
            request_body["observations"] = payload.observations
        for index, item in enumerate(payload.items):
            if item.notes:
                request_body["items"][index]["notes"] = item.notes

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{self._base_url}/orders",
                json=request_body,
                headers={"X-Internal-Api-Key": self._api_key},
            )
            response.raise_for_status()

    async def update_order_status(
        self,
        external_bot_id: str,
        status: str,
        reason: str | None = None,
    ) -> None:
        if not self._enabled:
            logger.info("admin backend order sync is disabled; skipping status sync")
            return
        if not self._api_key:
            logger.warning("internal api key is not configured; skipping admin backend status sync")
            return

        request_body: dict[str, object] = {"status": status}
        if reason:
            request_body["reason"] = reason

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.patch(
                f"{self._base_url}/orders/external/{external_bot_id}/status",
                json=request_body,
                headers={"X-Internal-Api-Key": self._api_key},
            )
            response.raise_for_status()
