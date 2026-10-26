"""Load multi-year daily history for the research universe from a provider."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from ..providers.base import MarketDataProvider
from ..schemas import OhlcvBar


@dataclass
class LoadedData:
    daily_by_symbol: dict[str, list[OhlcvBar]]
    benchmark_daily: list[OhlcvBar] | None
    missing: list[dict] = field(default_factory=list)  # [{"symbol", "reason"}]


async def load_daily(
    provider: MarketDataProvider,
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
            except Exception as exc:
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
            missing.append({"symbol": benchmark, "reason": f"benchmark unavailable, using universe average ({err})"})
    return LoadedData(daily_by_symbol=daily, benchmark_daily=bench_bars, missing=missing)
