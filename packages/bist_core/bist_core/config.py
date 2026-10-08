"""Application configuration, loaded from environment variables.

Every tunable (polling interval, scoring weights, alert cooldowns, provider
URLs, credentials) lives here so the deployment is driven purely by env vars /
``.env`` as required by the spec.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- General -----------------------------------------------------------
    app_name: str = "BIST Intelligence MVP"
    environment: str = "development"

    # Demo mode generates deterministic, clearly-fake data. It must never be
    # mixed with production data (the DataStatus is forced to DEMO).
    demo_mode: bool = Field(default=False, alias="DEMO_MODE")

    # --- Market data provider ---------------------------------------------
    # Which MarketDataProvider implementation to use: "bist" or "demo".
    market_data_provider: str = Field(default="bist", alias="MARKET_DATA_PROVIDER")
    bist_data_service_url: str = Field(
        default="http://localhost:8000", alias="BIST_DATA_SERVICE_URL"
    )
    provider_timeout_seconds: float = Field(default=10.0, alias="PROVIDER_TIMEOUT")
    # Quotes older than this (relative to the market timestamp) are STALE.
    stale_after_seconds: int = Field(default=180, alias="STALE_AFTER_SECONDS")

    # --- Ingestion ---------------------------------------------------------
    poll_interval_seconds: int = Field(default=60, alias="POLL_INTERVAL_SECONDS")
    signal_interval_seconds: int = Field(default=60, alias="SIGNAL_INTERVAL_SECONDS")

    # --- Storage -----------------------------------------------------------
    database_url: str = Field(
        default="postgresql+psycopg://bist:bist@localhost:5432/bist",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # --- AI analyzer -------------------------------------------------------
    # "mock" (deterministic, offline) or "anthropic".
    ai_provider: str = Field(default="mock", alias="AI_PROVIDER")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(
        default="claude-sonnet-5-5", alias="ANTHROPIC_MODEL"
    )

    # --- Telegram ----------------------------------------------------------
    telegram_enabled: bool = Field(default=False, alias="TELEGRAM_ENABLED")
    telegram_bot_token: str | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = Field(default=None, alias="TELEGRAM_CHAT_ID")

    # Alert cooldowns (seconds).
    alert_cooldown_seconds: int = Field(default=600, alias="ALERT_COOLDOWN_SECONDS")
    # A reversal bypasses the cooldown and is sent immediately.
    reversal_cooldown_seconds: int = Field(
        default=0, alias="REVERSAL_COOLDOWN_SECONDS"
    )
    # Only emit an alert when the score crosses a direction boundary or moves
    # more than this many points.
    alert_min_score_delta: float = Field(default=10.0, alias="ALERT_MIN_SCORE_DELTA")

    # --- Watchlist ---------------------------------------------------------
    default_watchlist: str = Field(
        default="KTLEV,THYAO,ASELS,TUPRS,EREGL", alias="DEFAULT_WATCHLIST"
    )

    @property
    def default_symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.default_watchlist.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
