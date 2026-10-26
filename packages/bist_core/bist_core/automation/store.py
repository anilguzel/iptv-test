"""A folder of per-symbol daily CSV files that grows a little every day.

New downloads are merged into the stored history. If the source has
re-adjusted its history since the last run (e.g. after a reverse split),
the overlapping days reveal the adjustment factor and the older stored rows
are rescaled by it, so the merged series has no artificial jump.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ..providers.csv_ohlcv import parse_ohlcv_csv
from ..schemas import OhlcvBar

HEADER = "Date,Open,High,Low,Close,Volume"
# Overlap close ratios further than this from 1.0 mean the source re-adjusted.
ADJUSTMENT_TOLERANCE = 0.02


def csv_path(directory: Path, symbol: str) -> Path:
    return directory / f"{symbol.upper()}.csv"


def read_store(path: Path, symbol: str) -> list[OhlcvBar]:
    if not path.exists():
        return []
    return parse_ohlcv_csv(path.read_text(encoding="utf-8"), symbol)


def write_store(path: Path, bars: list[OhlcvBar]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [HEADER] + [
        f"{b.timestamp.date().isoformat()},{b.open:.6g},{b.high:.6g},{b.low:.6g},{b.close:.6g},{b.volume:.0f}"
        for b in sorted(bars, key=lambda b: b.timestamp)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@dataclass
class MergeResult:
    bars: list[OhlcvBar]
    added: int                 # dates that were not stored before
    updated: int               # overlapping dates whose values changed
    rescale_factor: float | None  # set when older rows were re-adjusted


def _day(b: OhlcvBar) -> date:
    return b.timestamp.date()


def _same(a: OhlcvBar, b: OhlcvBar) -> bool:
    return all(abs(x - y) <= 1e-9 * max(1.0, abs(x)) for x, y in
               ((a.open, b.open), (a.high, b.high), (a.low, b.low), (a.close, b.close), (a.volume, b.volume)))


def merge_bars(old: list[OhlcvBar], new: list[OhlcvBar]) -> MergeResult:
    """Union by date; the new download wins on overlapping dates."""
    old_by = {_day(b): b for b in old}
    new_by = {_day(b): b for b in new}
    overlap = sorted(old_by.keys() & new_by.keys())

    factor = None
    ratios = [new_by[d].close / old_by[d].close for d in overlap if old_by[d].close > 0]
    if ratios:
        med = statistics.median(ratios)
        if abs(med - 1) > ADJUSTMENT_TOLERANCE:
            factor = med

    kept: list[OhlcvBar] = []
    for d, b in old_by.items():
        if d in new_by:
            continue
        if factor is not None:
            b = b.model_copy(update={
                "open": b.open * factor, "high": b.high * factor, "low": b.low * factor,
                "close": b.close * factor, "volume": b.volume / factor,
            })
        kept.append(b)

    merged = sorted(kept + list(new_by.values()), key=lambda b: b.timestamp)
    return MergeResult(
        bars=merged,
        added=len(new_by.keys() - old_by.keys()),
        updated=sum(1 for d in overlap if not _same(old_by[d], new_by[d])),
        rescale_factor=factor,
    )
