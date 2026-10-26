"""Deterministic demo macro provider.

Produces realistic but clearly fake EVDS-style series (DataStatus.DEMO) so the
macro context panel works offline / without an EVDS API key.
"""
from __future__ import annotations

import hashlib
import math
from datetime import UTC, date, datetime, timedelta

from ..config import Settings, get_settings
from ..schemas import MacroSeriesPoint, MacroSnapshot
from .base import MacroDataProvider
from .evds import build_snapshot

# Plausible base levels for well-known series; others get a deterministic base.
_BASE = {
    "TP.DK.USD.A": 34.0,
    "TP.DK.USD.S": 34.1,
    "TP.DK.EUR.A": 37.0,
    "TP.DK.EUR.S": 37.1,
    "TP.FG.J0": 2400.0,
}


def _seed(code: str) -> int:
    return int(hashlib.sha256(code.encode()).hexdigest(), 16) % 1000


def _base(code: str) -> float:
    return _BASE.get(code, 10.0 + _seed(code) % 90)


def _value(code: str, day: date) -> float:
    n = day.toordinal()
    base = _base(code)
    drift = 1 + (n % 365) * 0.0003  # slow upward drift
    wobble = 0.01 * math.sin((n + _seed(code)) / 9.0)
    return round(base * drift * (1 + wobble), 4)


class DemoMacroProvider(MacroDataProvider):
    name = "demo"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    async def get_series(
        self, series_codes: list[str], *, start: date, end: date | None = None
    ) -> list[MacroSnapshot]:
        end = end or datetime.now(UTC).date()
        today = datetime.now(UTC).date()
        out: list[MacroSnapshot] = []
        for code in series_codes:
            points: list[MacroSeriesPoint] = []
            d = start
            while d <= end:
                if d.weekday() < 5:  # business days only
                    points.append(MacroSeriesPoint(series_code=code, date=d, value=_value(code, d)))
                d += timedelta(days=1)
            out.append(build_snapshot(code, points, provider=self.name, now=today))
        return out

    async def get_latest(self, series_codes: list[str]) -> list[MacroSnapshot]:
        start = datetime.now(UTC).date() - timedelta(days=30)
        return await self.get_series(series_codes, start=start)
