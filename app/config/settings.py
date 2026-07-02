"""Centralized Pydantic Settings model.

All secrets and deployment options enter through environment variables or the
local .env file. Do not read environment variables directly elsewhere; inject
Settings so tests and local runs can override configuration consistently.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Pydantic Settings reads .env for local development and real environment
    # variables in production. extra=ignore lets operators keep unrelated values.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # App metadata.
    app_name: str = "ASADERO MC Bot Backend"
    app_env: Literal["local", "development", "staging", "production", "test"] = "local"
    app_debug: bool = False
    app_version: str = "0.1.0"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # External service URLs. PostgreSQL is the source of truth; Redis and Chroma
    # are rebuildable helpers.
    database_url: str = Field(
        default="postgresql+asyncpg://wen@localhost:5433/asadero_mc",
        repr=False,
    )
    redis_url: str = "redis://localhost:6379/0"
    chroma_host: str = "localhost"
    chroma_port: int = 8001

    # Telegram credentials must never be hardcoded in adapters or tests.
    telegram_bot_token: str = Field(default="", repr=False)
    telegram_webhook_secret: str = Field(default="", repr=False)

    # Gemini is the configured LLM path. Deterministic rules run first to avoid
    # spending credits on common menu/order messages.
    llm_provider: Literal["gemini"] = "gemini"
    gemini_model: str = "gemini-2.0-flash-lite"
    google_api_key: str = Field(default="", repr=False)
    gemini_api_key: str = Field(default="", repr=False)
    # Delivery fallback settings. Manual seeded zones still take priority over
    # distance estimates.
    delivery_origin_address: str = "Cra 3 # 48-06, Lagos II, Floridablanca, Santander, Colombia"
    delivery_base_price_cop: int = 2000
    delivery_price_per_km_cop: int = 2000
    delivery_round_to_cop: int = 500
    openrouteservice_api_key: str = Field(default="", repr=False)
    openrouteservice_base_url: str = "https://api.openrouteservice.org"

    log_level: str = "INFO"

    @property
    def resolved_google_api_key(self) -> str:
        # Keep both env var names accepted because Gemini docs and examples vary.
        return self.google_api_key or self.gemini_api_key


@lru_cache
def get_settings() -> Settings:
    # Cache settings so dependency injection and adapters share one parsed config.
    return Settings()
