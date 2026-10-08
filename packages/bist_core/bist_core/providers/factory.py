"""Provider selection driven purely by configuration."""
from __future__ import annotations

from ..config import Settings, get_settings
from .base import MarketDataProvider, NewsProvider
from .bist_data_service import BistDataServiceProvider
from .demo import DemoMarketDataProvider
from .news_mock import MockNewsProvider


def get_market_data_provider(settings: Settings | None = None) -> MarketDataProvider:
    settings = settings or get_settings()
    choice = "demo" if settings.demo_mode else settings.market_data_provider.lower()
    if choice == "demo":
        return DemoMarketDataProvider(settings)
    if choice in ("bist", "bist-data-service"):
        return BistDataServiceProvider(settings)
    raise ValueError(f"Unknown MARKET_DATA_PROVIDER: {settings.market_data_provider!r}")


def get_news_provider(settings: Settings | None = None) -> NewsProvider:
    settings = settings or get_settings()
    # Only a compliant mock is wired up for the MVP.
    return MockNewsProvider()
