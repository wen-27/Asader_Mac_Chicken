"""Local cache for WhatsApp media so admin previews do not depend on Meta URLs after receipt."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from app.config.settings import Settings


MEDIA_CACHE_DIR = Path(".local/whatsapp-media")


async def get_cached_or_fetch_whatsapp_media(settings: Settings, media_id: str) -> tuple[bytes, str]:
    cached = read_cached_whatsapp_media(media_id)
    if cached is not None:
        return cached
    return await fetch_and_cache_whatsapp_media(settings, media_id)


def read_cached_whatsapp_media(media_id: str) -> tuple[bytes, str] | None:
    safe_media_id = _safe_media_id(media_id)
    body_path = MEDIA_CACHE_DIR / f"{safe_media_id}.bin"
    meta_path = MEDIA_CACHE_DIR / f"{safe_media_id}.json"
    if not body_path.exists() or not meta_path.exists():
        return None
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    media_type = str(metadata.get("content_type") or "application/octet-stream")
    return body_path.read_bytes(), media_type


async def fetch_and_cache_whatsapp_media(settings: Settings, media_id: str) -> tuple[bytes, str]:
    if not settings.whatsapp_access_token:
        raise RuntimeError("whatsapp token is not configured")
    safe_media_id = _safe_media_id(media_id)
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}
    metadata_url = f"https://graph.facebook.com/{settings.whatsapp_graph_api_version}/{media_id}"
    async with httpx.AsyncClient(timeout=20) as client:
        metadata_response = await client.get(metadata_url, headers=headers)
        metadata_response.raise_for_status()
        metadata = metadata_response.json()
        media_url = metadata.get("url")
        if not media_url:
            raise RuntimeError("whatsapp media url missing")
        media_response = await client.get(media_url, headers=headers)
        media_response.raise_for_status()
    content_type = str(metadata.get("mime_type") or media_response.headers.get("content-type") or "application/octet-stream")
    MEDIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (MEDIA_CACHE_DIR / f"{safe_media_id}.bin").write_bytes(media_response.content)
    (MEDIA_CACHE_DIR / f"{safe_media_id}.json").write_text(
        json.dumps({"content_type": content_type}, ensure_ascii=True),
        encoding="utf-8",
    )
    return media_response.content, content_type


def _safe_media_id(media_id: str) -> str:
    return "".join(ch for ch in media_id if ch.isalnum() or ch in {"-", "_"})[:180]
