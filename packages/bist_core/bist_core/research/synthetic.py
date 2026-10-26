"""Synthetic daily data with a known answer, for validating the harness.

``momentum`` plants a real effect: a stock's excess return next week leans in
the direction of its last 4 weeks of excess return. With ``momentum=0`` there
is no exploitable pattern at all, so an honest walk-forward must find nothing
(rank IC ~ 0). If the harness "finds" an edge in pure noise, it is leaking.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import numpy as np

from ..schemas import OhlcvBar

DAYS_PER_WEEK = 5


def _daily_bars(symbol: str, weekly_log: np.ndarray, p0: float, start: date, rng: np.random.Generator) -> list[OhlcvBar]:
    bars: list[OhlcvBar] = []
    price = p0
    for w, wlog in enumerate(weekly_log):
        noise = rng.normal(0, 0.008, DAYS_PER_WEEK)
        daily = wlog / DAYS_PER_WEEK + (noise - noise.mean())  # sums exactly to wlog
        for d, dlog in enumerate(daily):
            day = start + timedelta(days=7 * w + d)
            open_ = price
            price = price * float(np.exp(dlog))
            wiggle = abs(rng.normal(0, 0.004))
            bars.append(
                OhlcvBar(
                    symbol=symbol,
                    timestamp=datetime(day.year, day.month, day.day, 15, 0, tzinfo=UTC),
                    open=round(open_, 4),
                    high=round(max(open_, price) * (1 + wiggle), 4),
                    low=round(min(open_, price) * (1 - wiggle), 4),
                    close=round(price, 4),
                    volume=float(rng.lognormal(13, 0.4)),
                )
            )
    return bars


def synthetic_universe(
    *,
    n_stocks: int = 30,
    n_weeks: int = 160,
    momentum: float = 0.0,
    seed: int = 0,
    start: date = date(2023, 1, 2),  # a Monday
) -> tuple[dict[str, list[OhlcvBar]], list[OhlcvBar]]:
    """Return (daily bars by symbol, daily benchmark bars named "XU100")."""
    rng = np.random.default_rng(seed)
    market = rng.normal(0.004, 0.03, n_weeks)  # weekly market log-returns (inflationary drift)
    excess = np.zeros((n_stocks, n_weeks))
    for w in range(n_weeks):
        drift = np.zeros(n_stocks)
        if momentum and w >= 4:
            past = excess[:, w - 4:w].sum(axis=1)
            sd = past.std()
            if sd > 0:
                drift = momentum * 0.02 * (past - past.mean()) / sd
        excess[:, w] = drift + rng.normal(0, 0.04, n_stocks)
        excess[:, w] -= excess[:, w].mean()  # excess is relative to the market

    daily = {
        f"SYN{i:02d}": _daily_bars(f"SYN{i:02d}", market + excess[i], float(rng.uniform(20, 200)), start, rng)
        for i in range(n_stocks)
    }
    bench = _daily_bars("XU100", market, 10_000.0, start, rng)
    return daily, bench
