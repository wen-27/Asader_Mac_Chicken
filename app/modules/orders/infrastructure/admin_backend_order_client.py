"""Internal HTTP client that syncs confirmed bot orders into the admin backend."""

from __future__ import annotations

import logging

import httpx

from app.config.settings import Settings
from app.modules.orders.domain.order import Order

logger = logging.getLogger(__name__)


class AdminBackendOrderClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.admin_backend_base_url.rstrip("/")
        self._api_key = settings.internal_api_key

    async def sync_confirmed_order(self, order: Order, chat_id: int) -> None:
        if not self._api_key:
            logger.warning("internal api key is not configured; skipping admin backend order sync")
            return

        payload = {
            "externalBotId": str(order.order_id.value),
            "chatId": str(chat_id),
            "customer": {
                "fullName": order.customer.name.value,
                "phone": order.customer.phone.value,
                "address": f"{order.customer.address.value} - {order.customer.neighborhood.value}",
            },
            "paymentMethod": str(order.payment_method.value),
            "observations": order.customer.observations or order.notes or None,
            "deliveryFeeCop": order.delivery_zone.delivery_price.amount,
            "items": [
                {
                    "productCode": item.product_code.value,
                    "productName": item.product_name.value,
                    "quantity": item.quantity,
                    "unitPriceCop": item.unit_price_snapshot.amount,
                    "notes": None,
                }
                for item in order.items
            ],
        }

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{self._base_url}/orders",
                json=payload,
                headers={"X-Internal-Api-Key": self._api_key},
            )
            response.raise_for_status()
