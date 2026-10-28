"""TCMB EVDS macro-data provider (REST API).

EVDS (Elektronik Veri Dağıtım Sistemi) serves the Central Bank of Türkiye's
macro / monetary time series — FX reference rates, policy & market rates, CPI,
etc. It is end-of-day / periodic data and never includes equity prices, so this
is a *context* layer, not the market feed.

Request format (quirky but official): the series/params sit right after the
path with no ``?``, and the API key goes in a ``key`` header::

    GET /service/evds/series=TP.DK.USD.A-TP.DK.EUR.A&startDate=01-01-2024&endDate=01-02-2024&type=json
    key: <EVDS_API_KEY>

Response JSON: ``{"items": [{"Tarih": "02-01-2024", "TP_DK_USD_A": "31.5", ...}]}``
where each series code's dots become underscores and values are strings.

A free API key is obtained from the EVDS profile page (see README). An official
EVDS MCP server also exists for conversational/ad-hoc access; this provider is
the programmatic path the backend uses.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import httpx

from ..config import Settings, get_settings
from ..enums import DataStatus
from ..schemas import MacroSeriesPoint, MacroSnapshot, OhlcvBar
from .base import MacroDataProvider

# Friendly display names for commonly tracked series. Unknown codes fall back
# to the raw code.
SERIES_NAMES: dict[str, str] = {
    "TP.DK.USD.A": "USD/TRY (alış)",
    "TP.DK.USD.S": "USD/TRY (satış)",
    "TP.DK.EUR.A": "EUR/TRY (alış)",
    "TP.DK.EUR.S": "EUR/TRY (satış)",
    "TP.FG.J0": "TÜFE (2003=100)",
}

# The API moved with the EVDS3 site (2025); the old host is kept as a fallback.
FALLBACK_BASE_URLS = (
    "https://evds3.tcmb.gov.tr/igmevdsms-dis",
    "https://evds2.tcmb.gov.tr/service/evds",
)
# Days per request when downloading long daily histories.
CHUNK_DAYS = 366

# How stale (in days) a macro observation may be before we flag it STALE. EVDS
# does not publish on weekends/holidays, so allow a few days.
MACRO_STALE_DAYS = 7


def series_name(code: str) -> str:
    return SERIES_NAMES.get(code, code)


def _fmt(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def _parse_date(value: str) -> date | None:
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _to_float(value) -> float | None:
    if value in (None, "", "ND", "null"):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def build_snapshot(code: str, points: list[MacroSeriesPoint], *, provider: str, now: date) -> MacroSnapshot:
    points = sorted(points, key=lambda p: p.date)
    latest = points[-1] if points else None
    previous = points[-2] if len(points) >= 2 else None
    change_pct = None
    if latest and previous and previous.value:
        change_pct = round((latest.value - previous.value) / previous.value * 100, 4)

    status = DataStatus.DEMO if provider == "demo" else DataStatus.DELAYED
    if latest and provider != "demo" and (now - latest.date).days > MACRO_STALE_DAYS:
        status = DataStatus.STALE

    return MacroSnapshot(
        series_code=code,
        name=series_name(code),
        latest_value=latest.value if latest else None,
        previous_value=previous.value if previous else None,
        change_percent=change_pct,
        as_of=latest.date if latest else None,
        provider=provider,
        data_status=status,
        points=points,
    )


class EvdsError(RuntimeError):
    pass


class EvdsMacroProvider(MacroDataProvider):
    name = "evds"

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self._client = client or httpx.AsyncClient(
            timeout=max(self.settings.provider_timeout_seconds, 30.0), follow_redirects=True
        )
        self._working_base: str | None = None

    def _headers(self) -> dict[str, str]:
        # EVDS accepts the key as a header (preferred) or a query param.
        return {"key": self.settings.evds_api_key} if self.settings.evds_api_key else {}

    def _bases(self) -> list[str]:
        ordered = [self._working_base, self.settings.evds_base_url.rstrip("/"), *FALLBACK_BASE_URLS]
        return list(dict.fromkeys(b for b in ordered if b))

    async def _items(self, series_codes: list[str], start: date, end: date) -> list[dict]:
        """Raw rows for one request, trying the known API hosts in turn."""
        if not self.settings.evds_api_key:
            raise EvdsError("EVDS_API_KEY is not set")
        query = f"series={'-'.join(series_codes)}&startDate={_fmt(start)}&endDate={_fmt(end)}&type=json"
        errors = []
        for base in self._bases():
            try:
                resp = await self._client.get(f"{base}/{query}", headers=self._headers())
                if resp.status_code != 200:
                    errors.append(f"{base}: HTTP {resp.status_code}")
                    continue
                payload = resp.json()
            except (httpx.HTTPError, ValueError) as exc:
                errors.append(f"{base}: {type(exc).__name__}")
                continue
            if isinstance(payload, dict) and isinstance(payload.get("items"), list):
                self._working_base = base
                return payload["items"]
            errors.append(f"{base}: unexpected response")
        raise EvdsError("; ".join(errors))

    async def get_series(
        self, series_codes: list[str], *, start: date, end: date | None = None
    ) -> list[MacroSnapshot]:
        if not series_codes:
            return []
        end = end or datetime.now(UTC).date()
        items: list[dict] = []
        chunk_start = start
        while chunk_start <= end:
            chunk_end = min(end, chunk_start + timedelta(days=CHUNK_DAYS - 1))
            items += await self._items(series_codes, chunk_start, chunk_end)
            chunk_start = chunk_end + timedelta(days=1)

        by_code: dict[str, list[MacroSeriesPoint]] = {c: [] for c in series_codes}
        for item in items:
            d = _parse_date(item.get("Tarih", ""))
            if d is None:
                continue
            for code in series_codes:
                val = _to_float(item.get(code.replace(".", "_")))
                if val is not None:
                    by_code[code].append(MacroSeriesPoint(series_code=code, date=d, value=val))

        today = datetime.now(UTC).date()
        return [build_snapshot(c, by_code[c], provider=self.name, now=today) for c in series_codes]

    async def get_latest(self, series_codes: list[str]) -> list[MacroSnapshot]:
        # Look back ~30 days so weekends/holidays still yield the last few points.
        start = datetime.now(UTC).date() - timedelta(days=30)
        return await self.get_series(series_codes, start=start)

    async def aclose(self) -> None:
        await self._client.aclose()


_PERIOD_DAYS = {"1mo": 31, "3mo": 92, "6mo": 183, "1y": 366, "2y": 731, "5y": 1827, "10y": 3653}


class EvdsHistoryProvider:
    """EVDS series as daily bars (open = high = low = close = value, volume 0),
    so the collect job can store FX rates next to stock prices."""

    name = "evds"

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self._macro = EvdsMacroProvider(settings, client)

    async def get_history(self, symbol: str, *, interval: str = "1d", limit: int = 120,
                          period: str | None = None) -> list[OhlcvBar]:
        if interval != "1d":
            raise ValueError("EVDS history is daily")
        end = datetime.now(UTC).date()
        start = end - timedelta(days=_PERIOD_DAYS.get(period or "1y", 366))
        snap, = await self._macro.get_series([symbol], start=start, end=end)
        if not snap.points:
            raise EvdsError(f"{symbol}: no observations")
        return [
            OhlcvBar(symbol=symbol.upper(), timestamp=datetime(p.date.year, p.date.month, p.date.day, tzinfo=UTC),
                     open=p.value, high=p.value, low=p.value, close=p.value, volume=0.0)
            for p in snap.points
        ]

    async def aclose(self) -> None:
        await self._macro.aclose()
