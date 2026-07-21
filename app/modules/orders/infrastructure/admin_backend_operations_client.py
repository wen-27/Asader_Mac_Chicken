"""Internal HTTP client for restaurant operation switches exposed by the admin backend."""

from __future__ import annotations

import logging

import httpx

from app.config.settings import Settings

logger = logging.getLogger(__name__)


class AdminBackendOperationsClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.admin_backend_base_url.rstrip("/")
        self._api_key = settings.internal_api_key
        self._enabled = settings.admin_backend_sync_enabled
        self._timeout = settings.admin_backend_timeout_seconds

    async def delivery_orders_enabled(self) -> bool:
        if not self._enabled:
            return True
        if not self._api_key:
            logger.warning("internal api key is not configured; assuming delivery orders are enabled")
            return True

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    f"{self._base_url}/operations/delivery-availability",
                    headers={"X-Internal-Api-Key": self._api_key},
                )
                response.raise_for_status()
        except Exception:
            logger.exception("failed to fetch delivery operation state; assuming delivery orders are enabled")
            return True

        data = response.json().get("data") or {}
        return bool(data.get("deliveryOrdersEnabled", True))
