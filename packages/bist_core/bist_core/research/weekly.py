"""Resample daily bars into weekly (ISO-week) bars."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..schemas import OhlcvBar

WeekKey = tuple[int, int]  # (ISO year, ISO week)


@dataclass(frozen=True)
class WeeklyBar:
    symbol: str
    week: WeekKey
    end_date: date  # last trading day in the week
    open: float
    high: float
    low: float
    close: float
    volume: float
    n_days: int


def week_key(d: date) -> WeekKey:
    iso = d.isocalendar()
    return (iso[0], iso[1])


def to_weekly(bars: list[OhlcvBar]) -> list[WeeklyBar]:
    """Group daily bars by ISO week. Bars with a missing/non-positive close are dropped."""
    groups: dict[WeekKey, list[OhlcvBar]] = {}
    for b in bars:
        if b.close is None or b.close <= 0:
            continue
        groups.setdefault(week_key(b.timestamp.date()), []).append(b)

    out: list[WeeklyBar] = []
    for wk in sorted(groups):
        g = sorted(groups[wk], key=lambda b: b.timestamp)
        out.append(
            WeeklyBar(
                symbol=g[0].symbol,
                week=wk,
                end_date=g[-1].timestamp.date(),
                open=g[0].open,
                high=max(b.high for b in g),
                low=min(b.low for b in g),
                close=g[-1].close,
                volume=sum(b.volume for b in g),
                n_days=len(g),
            )
        )
    return out
