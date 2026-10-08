"""Deterministic demo market-data provider.

Enabled with ``DEMO_MODE=true`` / ``MARKET_DATA_PROVIDER=demo``. Generates
realistic but clearly fake data (``DataStatus.DEMO``) so the whole pipeline can
be exercised offline. Demo data must never be presented as real.

Determinism: prices are a function of (symbol, minute-bucket) so repeated runs
and tests produce identical output.
"""
from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime, timedelta

from ..config import Settings, get_settings
from ..enums import DataStatus
from ..schemas import IntradayPoint, OhlcvBar, Quote
from .base import MarketDataProvider

_BASE_PRICES = {
    "KTLEV": 7.00,
    "THYAO": 300.0,
    "ASELS": 55.0,
    "TUPRS": 180.0,
    "EREGL": 42.0,
}


def _seed(symbol: str) -> int:
    return int(hashlib.sha256(symbol.upper().encode()).hexdigest(), 16) % 10_000


def _base_price(symbol: str) -> float:
    return _BASE_PRICES.get(symbol.upper(), 10.0 + _seed(symbol) % 90)


def _wave(symbol: str, minute: int) -> float:
    """A smooth, deterministic pseudo-random walk factor in roughly [-0.1, 0.1]."""
    s = _seed(symbol)
    return (
        0.06 * math.sin((minute + s) / 23.0)
        + 0.03 * math.sin((minute + s) / 7.0)
        + 0.015 * math.sin((minute + s) / 3.0)
    )


class DemoMarketDataProvider(MarketDataProvider):
    name = "demo"
    realtime = False

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def _quote_at(self, symbol: str, at: datetime) -> Quote:
        minute = int(at.timestamp() // 60)
        base = _base_price(symbol)
        price = round(base * (1 + _wave(symbol, minute)), 2)
        prev_close = round(base * (1 + _wave(symbol, minute - 390)), 2)  # ~prev session
        change = round(price - prev_close, 2)
        change_pct = round(change / prev_close * 100, 2) if prev_close else 0.0
        # Volume swells and spikes deterministically through the session.
        vol = int(500_000 + 2_000_000 * abs(_wave(symbol, minute)) + (minute % 97) * 5_000)
        return Quote(
            symbol=symbol.upper(),
            price=price,
            previous_close=prev_close,
            change=change,
            change_percent=change_pct,
            open=prev_close,
            high=round(price * 1.01, 2),
            low=round(price * 0.99, 2),
            volume=float(vol),
            timestamp=at,
            data_status=DataStatus.DEMO,
            provider=self.name,
            latency=0.001,
        )

    async def get_quote(self, symbol: str) -> Quote:
        return self._quote_at(symbol, datetime.now(UTC))

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        now = datetime.now(UTC)
        return [self._quote_at(s, now) for s in symbols]

    async def get_history(self, symbol: str, *, interval: str = "1d", limit: int = 120) -> list[OhlcvBar]:
        now = datetime.now(UTC)
        bars: list[OhlcvBar] = []
        for i in range(limit, 0, -1):
            day = now - timedelta(days=i)
            minute = int(day.timestamp() // 60)
            base = _base_price(symbol)
            close = round(base * (1 + _wave(symbol, minute)), 2)
            open_ = round(base * (1 + _wave(symbol, minute - 10)), 2)
            bars.append(
                OhlcvBar(
                    symbol=symbol.upper(),
                    timestamp=day,
                    open=open_,
                    high=round(max(open_, close) * 1.02, 2),
                    low=round(min(open_, close) * 0.98, 2),
                    close=close,
                    volume=float(1_000_000 + (minute % 500) * 1000),
                )
            )
        return bars

    async def get_intraday(self, symbol: str) -> list[IntradayPoint]:
        now = datetime.now(UTC)
        pts: list[IntradayPoint] = []
        cum_vol = 0.0
        for i in range(120, 0, -1):
            at = now - timedelta(minutes=i)
            q = self._quote_at(symbol, at)
            cum_vol += q.volume / 120.0
            pts.append(IntradayPoint(symbol=symbol.upper(), timestamp=at, price=q.price, volume=cum_vol))
        return pts
