"""BistDataServiceProvider against the response shapes in the service README."""
from __future__ import annotations

import asyncio

import httpx
from bist_core.config import Settings
from bist_core.enums import DataStatus
from bist_core.providers.bist_data_service import BistDataServiceProvider, period_for_limit


def _provider(handler, **settings) -> BistDataServiceProvider:
    s = Settings(BIST_DATA_SERVICE_URL="http://svc", **settings)
    p = BistDataServiceProvider(s)
    # Swap in a mock transport but keep the base_url/headers the provider configured.
    p._client = httpx.AsyncClient(
        base_url=p._client.base_url, headers=p._client.headers, transport=httpx.MockTransport(handler)
    )
    return p


def test_quotes_object_keyed_by_symbol_is_parsed():
    payload = {
        "count": 2,
        "missing": ["ZZZZ"],
        "quotes": {
            "THYAO": {"symbol": "THYAO", "price": 300.5, "day_high": 305, "day_low": 298,
                      "previous_close": 295, "volume": 1000, "exchange_time": "2026-01-02T12:00:00+03:00"},
            "GARAN": {"symbol": "GARAN", "price": 120.0, "stale": True, "updated_at": "2026-01-02T12:00:00Z"},
        },
    }
    p = _provider(lambda req: httpx.Response(200, json=payload))
    quotes = {q.symbol: q for q in asyncio.run(p.get_quotes(["THYAO", "GARAN", "ZZZZ"]))}
    assert set(quotes) == {"THYAO", "GARAN"}
    assert quotes["THYAO"].high == 305 and quotes["THYAO"].low == 298
    assert quotes["GARAN"].data_status == DataStatus.STALE  # provider-reported staleness honoured


def test_history_uses_period_time_field_and_skips_unclosed_bar():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(dict(req.url.params))
        seen["key"] = req.headers.get("X-API-Key")
        return httpx.Response(200, json={"symbol": "THYAO", "bars": [
            {"time": "2025-01-02T00:00:00Z", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
            {"time": "2025-01-03T00:00:00Z", "open": 1.5, "high": 2, "low": 1, "close": 1.8, "volume": 12},
            {"time": "2025-01-06T00:00:00Z", "open": 1.8, "high": 1.9, "low": 1.7, "close": None, "volume": 3},
        ]})

    p = _provider(handler, BIST_DATA_SERVICE_API_KEY="secret")
    bars = asyncio.run(p.get_history("THYAO", interval="1d", period="5y"))
    assert seen["period"] == "5y" and seen["interval"] == "1d"
    assert seen["key"] == "secret"
    assert [b.timestamp.date().isoformat() for b in bars] == ["2025-01-02", "2025-01-03"]


def test_period_for_limit():
    assert period_for_limit(120) == "6mo"
    assert period_for_limit(800) == "5y"
