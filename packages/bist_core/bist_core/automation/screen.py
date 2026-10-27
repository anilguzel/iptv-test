"""Pick the stocks worth researching: long history, real trading volume.

Applied to the stored CSVs before each research run, so the universe follows
the data instead of a hand-kept list: a stock that lists recently, dries up or
stops updating drops out on its own, and one that matures comes in.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .store import csv_path, read_store


@dataclass
class ScreenRules:
    min_years: float = 0.0           # first stored day at least this long before the last one
    min_median_value: float = 0.0    # median daily close x volume over the lookback (local currency)
    max_zero_volume_share: float = 1.0  # share of lookback days with zero volume (bad or halted data)
    max_stale_days: int | None = None   # last bar at most this many calendar days before the freshest stock
    lookback_days: int = 250         # about one trading year

    @property
    def active(self) -> bool:
        return bool(self.min_years or self.min_median_value or self.max_zero_volume_share < 1.0
                    or self.max_stale_days is not None)


def screen_symbols(folder: Path, symbols: list[str], rules: ScreenRules) -> dict:
    """{"kept": [...], "rows": [{symbol, years, median_value, zero_share, last, reasons}]}"""
    stats = []
    for sym in symbols:
        bars = read_store(csv_path(folder, sym), sym)
        if not bars:
            stats.append({"symbol": sym, "years": 0.0, "median_value": 0.0, "zero_share": 1.0,
                          "last": None, "reasons": ["veri yok"]})
            continue
        recent = bars[-rules.lookback_days:]
        first, last = bars[0].timestamp.date(), bars[-1].timestamp.date()
        stats.append({
            "symbol": sym,
            "years": round((last - first).days / 365.25, 2),
            "median_value": round(statistics.median(b.close * b.volume for b in recent), 2),
            "zero_share": round(sum(1 for b in recent if b.volume <= 0) / len(recent), 4),
            "last": last.isoformat(),
            "reasons": [],
        })
    dated = [date.fromisoformat(s["last"]) for s in stats if s["last"]]
    freshest = max(dated) if dated else None
    for s in stats:
        if s["last"] is None:
            continue
        if s["years"] < rules.min_years:
            s["reasons"].append(f"geçmiş {s['years']:.1f} yıl < {rules.min_years:g}")
        if s["median_value"] < rules.min_median_value:
            s["reasons"].append(f"medyan işlem hacmi {s['median_value']:,.0f} < {rules.min_median_value:,.0f}")
        if s["zero_share"] > rules.max_zero_volume_share:
            s["reasons"].append(f"hacimsiz gün oranı %{s['zero_share'] * 100:.0f}")
        if rules.max_stale_days is not None and freshest is not None:
            lag = (freshest - date.fromisoformat(s["last"])).days
            if lag > rules.max_stale_days:
                s["reasons"].append(f"son veri {s['last']} ({lag} gün geride)")
    stats.sort(key=lambda s: -s["median_value"])
    return {"kept": [s["symbol"] for s in stats if not s["reasons"]], "rows": stats}
