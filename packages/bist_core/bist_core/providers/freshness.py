"""Freshness classification shared by all providers."""
from __future__ import annotations

from datetime import UTC, datetime

from ..enums import DataStatus


def classify_freshness(
    market_timestamp: datetime,
    *,
    provider_realtime: bool,
    stale_after_seconds: int,
    now: datetime | None = None,
) -> DataStatus:
    """Return the appropriate :class:`DataStatus` for a quote.

    A non-realtime provider is at best ``DELAYED``. Once the quote is older
    than ``stale_after_seconds`` it becomes ``STALE`` regardless of provider.
    """
    now = now or datetime.now(UTC)
    if market_timestamp.tzinfo is None:
        market_timestamp = market_timestamp.replace(tzinfo=UTC)
    age = (now - market_timestamp).total_seconds()

    if age > stale_after_seconds:
        return DataStatus.STALE
    return DataStatus.LIVE if provider_realtime else DataStatus.DELAYED
