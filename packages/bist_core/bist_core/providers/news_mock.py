"""Mock news / KAP provider.

We do NOT scrape any site in violation of its terms. This mock returns a small
deterministic set of events so the news→price correlation logic can be built
and tested. A licensed KAP provider implements the same ``NewsProvider``
interface later.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ..enums import NewsCategory
from ..schemas import NewsEvent
from .base import NewsProvider

# Deterministic seed events keyed by symbol.
_SEED_NEWS: dict[str, list[tuple[int, str, NewsCategory, int]]] = {
    "KTLEV": [(45, "Şirket yeni tedarik sözleşmesi imzaladı", NewsCategory.CONTRACT, 3)],
    "THYAO": [(120, "Çeyreklik yolcu trafiği açıklandı", NewsCategory.FINANCIAL, 2)],
}


class MockNewsProvider(NewsProvider):
    name = "mock-news"

    async def get_news(self, symbol: str, *, since: datetime | None = None) -> list[NewsEvent]:
        now = datetime.now(UTC)
        # Anchor to a stable per-day reference so repeated polls yield identical
        # timestamps and de-duplicate cleanly, instead of drifting with now().
        ref = now.replace(hour=12, minute=0, second=0, microsecond=0)
        events: list[NewsEvent] = []
        for minutes_ago, headline, category, importance in _SEED_NEWS.get(symbol.upper(), []):
            ts = ref - timedelta(minutes=minutes_ago)
            if since and ts < since:
                continue
            events.append(
                NewsEvent(
                    symbol=symbol.upper(),
                    timestamp=ts,
                    headline=headline,
                    category=category,
                    importance=importance,
                    source=self.name,
                )
            )
        return events
