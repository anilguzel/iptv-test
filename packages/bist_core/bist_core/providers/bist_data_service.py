"""Adapter for the open-source ``bist-data-service`` (Armert-Labs).

That service exposes ``/quote/{symbol}``, ``/quotes?symbols=``, ``/all``,
``/history/{symbol}``, ``/intraday/{symbol}`` and an SSE ``/stream`` endpoint,
serving ~15 min delayed BIST data (Yahoo Finance + İş Yatırım fallback).

Response shapes follow the service README:
  * ``/quote``   -> ``price, previous_close, change, change_percent, open,
    day_high, day_low, volume, exchange_time, bar_time, updated_at, stale, ...``
  * ``/quotes``  -> ``{"count", "missing": [...], "quotes": {SYMBOL: Quote}}``
    (an object keyed by symbol; unknown symbols are listed in ``missing``)
  * ``/history`` -> ``{"bars": [{"time", "open", "high", "low", "close", "volume"}]}``
    with ``period`` (1d..max) and ``interval`` (1m..3mo) query params; ``close``
    may be null for a bar that has not closed yet.
An ``X-API-Key`` header is sent when ``BIST_DATA_SERVICE_API_KEY`` is set.

We treat it strictly as an external provider behind this adapter and never
fork or mutate it. Its data is delayed, so every quote we emit is DELAYED (or
STALE once too old) — never LIVE.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime

import httpx

from ..config import Settings, get_settings
from ..enums import DataStatus
from ..schemas import IntradayPoint, OhlcvBar, Quote
from .base import MarketDataProvider
from .freshness import classify_freshness


def _parse_ts(value) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, (int, float)):
        # Accept seconds or milliseconds epoch.
        v = float(value)
        return datetime.fromtimestamp(v / 1000 if v > 1e11 else v, tz=UTC)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _f(value, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _first(raw: dict, *keys):
    for k in keys:
        v = raw.get(k)
        if v is not None:
            return v
    return None


def period_for_limit(limit: int) -> str:
    """Smallest documented ``period`` that covers ``limit`` daily bars."""
    for max_bars, period in ((5, "5d"), (22, "1mo"), (66, "3mo"), (130, "6mo"), (260, "1y"), (520, "2y"), (1300, "5y")):
        if limit <= max_bars:
            return period
    return "max"


class BistDataServiceProvider(MarketDataProvider):
    name = "bist-data-service"
    realtime = False  # ~15 min delayed. NEVER report LIVE.

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        headers = {}
        if self.settings.bist_data_service_api_key:
            headers["X-API-Key"] = self.settings.bist_data_service_api_key
        self._client = client or httpx.AsyncClient(
            base_url=self.settings.bist_data_service_url.rstrip("/"),
            timeout=self.settings.provider_timeout_seconds,
            headers=headers,
        )

    # -- normalisation ----------------------------------------------------- #
    def _to_quote(self, symbol: str, raw: dict, latency: float) -> Quote:
        price = _f(_first(raw, "price", "last", "close")) or 0.0
        prev = _f(_first(raw, "previous_close", "previousClose", "prev_close"))
        change = _f(raw.get("change"))
        change_pct = _f(_first(raw, "change_percent", "changePercent", "change_pct"))
        if change is None and prev:
            change = round(price - prev, 6)
        if change_pct is None and prev:
            change_pct = round((price - prev) / prev * 100, 6)

        market_ts = _parse_ts(_first(raw, "exchange_time", "bar_time", "updated_at", "timestamp", "time"))
        status = classify_freshness(
            market_ts,
            provider_realtime=self.realtime,
            stale_after_seconds=self.settings.stale_after_seconds,
        )
        # Honour an explicit provider-reported staleness (downgrade only).
        if raw.get("stale") is True or str(raw.get("data_status") or "").upper() == "STALE":
            status = DataStatus.STALE

        return Quote(
            symbol=symbol.upper(),
            price=price,
            previous_close=prev,
            change=change,
            change_percent=change_pct,
            open=_f(raw.get("open")),
            high=_f(_first(raw, "day_high", "high")),
            low=_f(_first(raw, "day_low", "low")),
            volume=_f(raw.get("volume"), 0.0) or 0.0,
            timestamp=market_ts,
            data_status=status,
            provider=self.name,
            latency=round(latency, 4),
        )

    @staticmethod
    def _bars_from(payload, symbol: str) -> list[OhlcvBar]:
        rows = payload if isinstance(payload, list) else payload.get("bars") or payload.get("data") or []
        bars: list[OhlcvBar] = []
        for row in rows:
            close = _f(row.get("close"))
            if close is None or close <= 0:
                continue  # bar not closed yet (README: close may be null) or bad row
            bars.append(
                OhlcvBar(
                    symbol=symbol.upper(),
                    timestamp=_parse_ts(_first(row, "time", "timestamp", "date")),
                    open=_f(row.get("open")) or close,
                    high=_f(row.get("high")) or close,
                    low=_f(row.get("low")) or close,
                    close=close,
                    volume=_f(row.get("volume"), 0.0) or 0.0,
                )
            )
        bars.sort(key=lambda b: b.timestamp)
        return bars

    # -- interface --------------------------------------------------------- #
    async def get_quote(self, symbol: str) -> Quote:
        start = time.perf_counter()
        resp = await self._client.get(f"/quote/{symbol.upper()}")
        resp.raise_for_status()
        latency = time.perf_counter() - start
        return self._to_quote(symbol, resp.json(), latency)

    async def get_quotes(self, symbols: list[str]) -> list[Quote]:
        start = time.perf_counter()
        resp = await self._client.get("/quotes", params={"symbols": ",".join(s.upper() for s in symbols)})
        resp.raise_for_status()
        latency = time.perf_counter() - start
        payload = resp.json()
        quotes = payload.get("quotes") if isinstance(payload, dict) else payload
        out: list[Quote] = []
        if isinstance(quotes, dict):  # documented shape: {SYMBOL: Quote}
            for sym, row in quotes.items():
                if isinstance(row, dict):
                    out.append(self._to_quote(row.get("symbol") or sym, row, latency))
        elif isinstance(quotes, list):  # tolerate a list shape too
            for row in quotes:
                sym = isinstance(row, dict) and (row.get("symbol") or row.get("ticker"))
                if sym:
                    out.append(self._to_quote(sym, row, latency))
        return out

    async def get_history(
        self, symbol: str, *, interval: str = "1d", limit: int = 120, period: str | None = None
    ) -> list[OhlcvBar]:
        params = {"interval": interval, "period": period or period_for_limit(limit)}
        resp = await self._client.get(f"/history/{symbol.upper()}", params=params)
        resp.raise_for_status()
        bars = self._bars_from(resp.json(), symbol)
        # With an explicit period the caller wants the whole range; otherwise trim.
        return bars if period else bars[-limit:]

    async def get_intraday(self, symbol: str) -> list[IntradayPoint]:
        resp = await self._client.get(f"/intraday/{symbol.upper()}")
        resp.raise_for_status()
        payload = resp.json()
        rows = payload if isinstance(payload, list) else payload.get("points") or payload.get("bars") or payload.get("data") or []
        pts: list[IntradayPoint] = []
        for row in rows:
            price = _f(_first(row, "price", "close"))
            if price is None or price <= 0:
                continue
            pts.append(
                IntradayPoint(
                    symbol=symbol.upper(),
                    timestamp=_parse_ts(_first(row, "time", "timestamp")),
                    price=price,
                    volume=_f(row.get("volume"), 0.0) or 0.0,
                )
            )
        return pts

    async def aclose(self) -> None:
        await self._client.aclose()
