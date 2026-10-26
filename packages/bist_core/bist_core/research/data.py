"""Load multi-year daily history for the research universe from a provider."""
from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Protocol

from ..schemas import OhlcvBar

# A day-over-day move larger than this (in log terms, ~+65% / -40%) is flagged:
# it may be a genuine micro-cap move or an unadjusted split. Check before trusting.
JUMP_LOG_THRESHOLD = 0.5


class HistoryProvider(Protocol):
    name: str

    async def get_history(
        self, symbol: str, *, interval: str = "1d", limit: int = 120, period: str | None = None
    ) -> list[OhlcvBar]: ...


@dataclass
class LoadedData:
    daily_by_symbol: dict[str, list[OhlcvBar]]
    benchmark_daily: list[OhlcvBar] | None
    missing: list[dict] = field(default_factory=list)  # [{"symbol", "reason"}]


def detect_jumps(daily_by_symbol: dict[str, list[OhlcvBar]], limit: int = 30) -> list[dict]:
    """Large single-day moves: possible unadjusted splits or data errors."""
    out: list[dict] = []
    for sym, bars in sorted(daily_by_symbol.items()):
        for prev, cur in pairwise(bars):
            if prev.close > 0 and cur.close > 0 and abs(math.log(cur.close / prev.close)) > JUMP_LOG_THRESHOLD:
                out.append({
                    "symbol": sym,
                    "date": cur.timestamp.date().isoformat(),
                    "change": round(cur.close / prev.close - 1, 4),
                })
    return out[:limit]


async def load_daily(
    provider: HistoryProvider,
    symbols: list[str],
    *,
    years: float = 3.0,
    period: str = "5y",
    benchmark: str | None = "XU100",
    concurrency: int = 5,
) -> LoadedData:
    cutoff = datetime.now(UTC) - timedelta(days=int(365.25 * years))
    sem = asyncio.Semaphore(concurrency)

    async def fetch(sym: str) -> tuple[str, list[OhlcvBar] | None, str | None]:
        async with sem:
            try:
                bars = await provider.get_history(sym, interval="1d", period=period)
            except Exception as exc:  # report per symbol, keep going
                return sym, None, f"{type(exc).__name__}: {exc}"[:200]
        bars = [b for b in bars if b.timestamp >= cutoff]
        if not bars:
            return sym, None, "no bars in the requested window"
        return sym, bars, None

    results = await asyncio.gather(*(fetch(s) for s in symbols))
    daily: dict[str, list[OhlcvBar]] = {}
    missing: list[dict] = []
    for sym, bars, err in results:
        if bars:
            daily[sym] = bars
        else:
            missing.append({"symbol": sym, "reason": err})

    bench_bars: list[OhlcvBar] | None = None
    if benchmark:
        _, bench_bars, err = await fetch(benchmark)
        if err:
            missing.append({"symbol": benchmark, "reason": f"benchmark unavailable ({err})"})
    return LoadedData(daily_by_symbol=daily, benchmark_daily=bench_bars, missing=missing)
