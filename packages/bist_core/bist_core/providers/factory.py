"""Provider selection driven purely by configuration."""
from __future__ import annotations

from ..config import Settings, get_settings
from .base import MacroDataProvider, MarketDataProvider, NewsProvider
from .bist_data_service import BistDataServiceProvider
from .demo import DemoMarketDataProvider
from .evds import EvdsMacroProvider
from .macro_demo import DemoMacroProvider
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


def get_macro_provider(settings: Settings | None = None) -> MacroDataProvider | None:
    settings = settings or get_settings()
    choice = "demo" if settings.demo_mode else settings.macro_provider.lower()
    if choice in ("none", "off", "disabled"):
        return None
    if choice == "demo":
        return DemoMacroProvider(settings)
    if choice == "evds":
        return EvdsMacroProvider(settings)
    raise ValueError(f"Unknown MACRO_PROVIDER: {settings.macro_provider!r}")
