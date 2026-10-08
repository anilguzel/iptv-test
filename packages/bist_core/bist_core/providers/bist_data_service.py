"""Adapter for the open-source ``bist-data-service`` (Armert-Labs).

That service exposes ``/quote/{symbol}``, ``/quotes?symbols=``, ``/all``,
``/history/{symbol}``, ``/intraday/{symbol}`` and an SSE ``/stream`` endpoint,
serving ~15 min delayed BIST data (Yahoo Finance + İş Yatırım fallback).

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
        return datetime.fromtimestamp(float(value), tz=UTC)
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


class BistDataServiceProvider(MarketDataProvider):
    name = "bist-data-service"
    realtime = False  # ~15 min delayed. NEVER report LIVE.

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self._client = client or httpx.AsyncClient(
            base_url=self.settings.bist_data_service_url.rstrip("/"),
            timeout=self.settings.provider_timeout_seconds,
        )

    # -- normalisation ----------------------------------------------------- #
    def _to_quote(self, symbol: str, raw: dict, latency: float) -> Quote:
        price = _f(raw.get("price") or raw.get("last") or raw.get("close")) or 0.0
        prev = _f(raw.get("previous_close") or raw.get("previousClose") or raw.get("prev_close"))
        change = _f(raw.get("change"))
        change_pct = _f(raw.get("change_percent") or raw.get("changePercent") or raw.get("change_pct"))
        if change is None and prev:
            change = round(price - prev, 6)
        if change_pct is None and prev:
            change_pct = round((price - prev) / prev * 100, 6) if prev else None

        market_ts = _parse_ts(raw.get("timestamp") or raw.get("time") or raw.get("market_timestamp"))
        status = classify_freshness(
            market_ts,
            provider_realtime=self.realtime,
            stale_after_seconds=self.settings.stale_after_seconds,
        )
        # Honour an explicit provider-reported status downgrade only.
        reported = str(raw.get("data_status") or "").upper()
        if reported == "STALE":
            status = DataStatus.STALE

        return Quote(
            symbol=symbol.upper(),
            price=price,
            previous_close=prev,
            change=change,
            change_percent=change_pct,
            open=_f(raw.get("open")),
            high=_f(raw.get("high")),
            low=_f(raw.get("low")),
            volume=_f(raw.get("volume"), 0.0) or 0.0,
            timestamp=market_ts,
            data_status=status,
            provider=self.name,
            latency=round(latency, 4),
        )

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
        rows = payload if isinstance(payload, list) else payload.get("quotes") or payload.get("data") or []
        out: list[Quote] = []
        for row in rows:
            sym = row.get("symbol") or row.get("ticker")
            if sym:
                out.append(self._to_quote(sym, row, latency))
        return out

    async def get_history(self, symbol: str, *, interval: str = "1d", limit: int = 120) -> list[OhlcvBar]:
        resp = await self._client.get(
            f"/history/{symbol.upper()}", params={"interval": interval, "limit": limit}
        )
        resp.raise_for_status()
        payload = resp.json()
        rows = payload if isinstance(payload, list) else payload.get("bars") or payload.get("data") or []
        bars: list[OhlcvBar] = []
        for row in rows:
            bars.append(
                OhlcvBar(
                    symbol=symbol.upper(),
                    timestamp=_parse_ts(row.get("timestamp") or row.get("date")),
                    open=_f(row.get("open")) or 0.0,
                    high=_f(row.get("high")) or 0.0,
                    low=_f(row.get("low")) or 0.0,
                    close=_f(row.get("close")) or 0.0,
                    volume=_f(row.get("volume"), 0.0) or 0.0,
                )
            )
        return bars

    async def get_intraday(self, symbol: str) -> list[IntradayPoint]:
        resp = await self._client.get(f"/intraday/{symbol.upper()}")
        resp.raise_for_status()
        payload = resp.json()
        rows = payload if isinstance(payload, list) else payload.get("points") or payload.get("data") or []
        pts: list[IntradayPoint] = []
        for row in rows:
            pts.append(
                IntradayPoint(
                    symbol=symbol.upper(),
                    timestamp=_parse_ts(row.get("timestamp") or row.get("time")),
                    price=_f(row.get("price") or row.get("close")) or 0.0,
                    volume=_f(row.get("volume"), 0.0) or 0.0,
                )
            )
        return pts

    async def aclose(self) -> None:
        await self._client.aclose()
