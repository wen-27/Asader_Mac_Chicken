"""Gemini LLM adapter. Keep provider-specific request/response handling out of application use cases."""

from __future__ import annotations

import httpx
from typing import Optional

from app.config.settings import Settings
from app.shared.domain.exceptions import InvalidValueError


class GeminiLLMClient:
    def __init__(
        self,
        settings: Settings,
        model: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        if not settings.resolved_google_api_key:
            raise InvalidValueError("gemini api key is not configured")
        self._api_key = settings.resolved_google_api_key
        self._model = model or settings.gemini_model
        self._client = client

    async def complete(self, prompt: str) -> str:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._model}:generateContent"
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        if self._client is None:
            async with httpx.AsyncClient(timeout=30) as client:
                data = await self._post(client, url, payload)
        else:
            data = await self._post(self._client, url, payload)
        return _extract_text(data)

    async def _post(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        response = await client.post(url, json=payload, headers={"x-goog-api-key": self._api_key})
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise InvalidValueError(
                f"gemini request failed with status {exc.response.status_code}"
            ) from exc
        return response.json()


def _extract_text(data: dict[str, object]) -> str:
    candidates = data.get("candidates", [])
    if not isinstance(candidates, list) or not candidates:
        return ""
    first = candidates[0]
    if not isinstance(first, dict):
        return ""
    content = first.get("content", {})
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts", [])
    if not isinstance(parts, list):
        return ""
    return "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
