"""Daily history from Yahoo Finance's chart endpoint (no API key).

The same source bist-data-service uses under the hood, so it covers BIST
(``THYAO`` -> ``THYAO.IS``, index ``XU100`` -> ``XU100.IS``) as well as US
stocks (no suffix). History only.

Caveat: this endpoint is unofficial. Yahoo's terms may restrict automated
access, it can rate-limit or change without notice. Keep usage light (one
daily batch). We identify ourselves honestly instead of imitating a browser.
"""
from __future__ import annotations

from datetime import UTC, datetime

import httpx

from ..config import Settings, get_settings
from ..schemas import OhlcvBar

USER_AGENT = "bist-intelligence/0.1 (personal research; daily batch)"


class YahooDataError(ValueError):
    pass


def parse_chart(payload: dict, symbol: str) -> list[OhlcvBar]:
    chart = payload.get("chart") or {}
    if chart.get("error"):
        err = chart["error"]
        raise YahooDataError(f"{symbol}: {err.get('code')}: {err.get('description')}")
    results = chart.get("result") or []
    if not results:
        raise YahooDataError(f"{symbol}: empty chart result")
    r = results[0]
    stamps = r.get("timestamp") or []
    quote = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    adj = ((r.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose")
    offset = int((r.get("meta") or {}).get("gmtoffset") or 0)

    def at(key: str, i: int):
        values = quote.get(key) or []
        return values[i] if i < len(values) else None

    bars: list[OhlcvBar] = []
    for i, ts in enumerate(stamps):
        close = at("close", i)
        if close is None or close <= 0:
            continue
        a = adj[i] if adj and i < len(adj) and adj[i] else None
        factor = a / close if a else 1.0  # split/dividend adjustment
        local = datetime.fromtimestamp(ts + offset, tz=UTC)  # exchange-local trading date
        o, h, lo = at("open", i) or close, at("high", i) or close, at("low", i) or close
        bars.append(
            OhlcvBar(
                symbol=symbol.upper(),
                timestamp=datetime(local.year, local.month, local.day, tzinfo=UTC),
                open=o * factor,
                high=h * factor,
                low=lo * factor,
                close=close * factor,
                volume=float(at("volume", i) or 0.0),
            )
        )
    if not bars:
        raise YahooDataError(f"{symbol}: chart had no usable rows")
    bars.sort(key=lambda b: b.timestamp)
    return bars


class YahooChartProvider:
    name = "yahoo"

    def __init__(self, settings: Settings | None = None, *, suffix: str = "", client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self.suffix = suffix
        self._client = client or httpx.AsyncClient(
            base_url=self.settings.yahoo_base_url.rstrip("/"),
            timeout=max(self.settings.provider_timeout_seconds, 30.0),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )

    def yahoo_symbol(self, symbol: str) -> str:
        s = symbol.strip().upper()
        if s.startswith("^") or "." in s:
            return s
        return f"{s}{self.suffix}"

    async def get_history(
        self, symbol: str, *, interval: str = "1d", limit: int = 120, period: str | None = None
    ) -> list[OhlcvBar]:
        if interval != "1d":
            raise ValueError("YahooChartProvider only serves daily bars")
        params = {"range": period or "5y", "interval": "1d", "events": "split,div"}
        resp = await self._client.get(f"/v8/finance/chart/{self.yahoo_symbol(symbol)}", params=params)
        if resp.status_code != 200:
            body = resp.text[:120].replace("\n", " ")
            raise YahooDataError(f"{symbol}: HTTP {resp.status_code} ({body})")
        bars = parse_chart(resp.json(), symbol)
        return bars if period else bars[-limit:]

    async def aclose(self) -> None:
        await self._client.aclose()
