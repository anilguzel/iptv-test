"""Daily history from Stooq (free CSV downloads, no API key).

Used by the research module for markets bist-data-service doesn't cover, e.g.
US stocks (``SMTK`` -> ``smtk.us``). History only: no quotes, no intraday.
Symbols that already contain a dot (``iwm.us``) or start with ``^`` (indices)
are passed through unchanged.
"""
from __future__ import annotations

import httpx

from ..config import Settings, get_settings
from ..schemas import OhlcvBar
from .csv_ohlcv import parse_ohlcv_csv


class StooqProvider:
    name = "stooq"

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self._client = client or httpx.AsyncClient(
            base_url=self.settings.stooq_base_url.rstrip("/"),
            timeout=max(self.settings.provider_timeout_seconds, 30.0),
            follow_redirects=True,
        )

    def stooq_symbol(self, symbol: str) -> str:
        s = symbol.strip().lower()
        if s.startswith("^") or "." in s:
            return s
        return f"{s}{self.settings.stooq_suffix}"

    async def get_history(
        self, symbol: str, *, interval: str = "1d", limit: int = 120, period: str | None = None
    ) -> list[OhlcvBar]:
        if interval != "1d":
            raise ValueError("StooqProvider only serves daily bars")
        resp = await self._client.get("/q/d/l/", params={"s": self.stooq_symbol(symbol), "i": "d"})
        resp.raise_for_status()
        bars = parse_ohlcv_csv(resp.text, symbol)
        # Stooq returns the full history; callers filter by date. Trim only
        # when no period was asked for.
        return bars if period else bars[-limit:]

    async def aclose(self) -> None:
        await self._client.aclose()
