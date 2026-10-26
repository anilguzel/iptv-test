"""Parse daily OHLCV CSV files (Stooq downloads, Yahoo Finance exports, ...).

Accepted headers (case-insensitive): Date, Open, High, Low, Close, Volume and
optionally "Adj Close". Nasdaq.com exports ("Close/Last", "$" prices,
MM/DD/YYYY dates) are accepted too. When "Adj Close" is present (Yahoo export), all prices
are scaled by Adj Close / Close so splits and dividends don't show up as fake
jumps.
"""
from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from pathlib import Path

from ..schemas import OhlcvBar


class CsvDataError(ValueError):
    pass


HEADER_ALIASES = {"close/last": "close", "adj. close": "adj close", "adjusted close": "adj close"}


def _num(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value or value.lower() in {"null", "nan", "n/a", "-"}:
        return None
    try:
        return float(value.replace(",", "").replace("$", ""))
    except ValueError:
        return None


def _date(value: str) -> datetime | None:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y", "%Y%m%d"):
        try:
            d = datetime.strptime(value, fmt)
            return datetime(d.year, d.month, d.day, tzinfo=UTC)
        except ValueError:
            continue
    return None


def parse_ohlcv_csv(text: str, symbol: str) -> list[OhlcvBar]:
    text = text.lstrip("﻿").strip()
    if not text:
        raise CsvDataError(f"{symbol}: empty response")
    reader = csv.DictReader(io.StringIO(text))
    fields = {f.strip().lower(): f for f in (reader.fieldnames or [])}
    # Header aliases used by other exporters, e.g. Nasdaq.com's "Close/Last".
    for alias, canonical in HEADER_ALIASES.items():
        if alias in fields and canonical not in fields:
            fields[canonical] = fields[alias]
    if not {"date", "close"} <= fields.keys():
        # Stooq answers unknown symbols / throttling with a plain-text line.
        raise CsvDataError(f"{symbol}: not an OHLCV CSV (starts with {text[:80]!r})")

    def col(row: dict, name: str) -> str | None:
        key = fields.get(name)
        return row.get(key) if key else None

    bars: list[OhlcvBar] = []
    for row in reader:
        ts = _date(col(row, "date") or "")
        close = _num(col(row, "close"))
        if ts is None or close is None or close <= 0:
            continue
        adj = _num(col(row, "adj close"))
        factor = adj / close if adj and adj > 0 else 1.0
        o = _num(col(row, "open")) or close
        h = _num(col(row, "high")) or max(o, close)
        lo = _num(col(row, "low")) or min(o, close)
        bars.append(
            OhlcvBar(
                symbol=symbol.upper(),
                timestamp=ts,
                open=o * factor,
                high=h * factor,
                low=lo * factor,
                close=close * factor,
                volume=_num(col(row, "volume")) or 0.0,
            )
        )
    if not bars:
        raise CsvDataError(f"{symbol}: CSV had no usable rows")
    bars.sort(key=lambda b: b.timestamp)
    return bars


class CsvDirProvider:
    """Daily history from a folder of CSV files named ``<SYMBOL>.csv``.

    Lets the research run on uploaded/downloaded data (e.g. Yahoo Finance
    "Historical Data -> Download") with no network access at all.
    """

    name = "csv"

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def symbols(self) -> list[str]:
        return sorted(p.stem.upper() for p in self.directory.glob("*.csv"))

    def _path(self, symbol: str) -> Path:
        for p in self.directory.glob("*.csv"):
            if p.stem.upper() == symbol.upper():
                return p
        raise FileNotFoundError(f"{symbol}.csv not found in {self.directory}")

    async def get_history(
        self, symbol: str, *, interval: str = "1d", limit: int = 120, period: str | None = None
    ) -> list[OhlcvBar]:
        if interval != "1d":
            raise ValueError("CsvDirProvider only serves daily bars")
        bars = parse_ohlcv_csv(self._path(symbol).read_text(encoding="utf-8-sig"), symbol)
        return bars if period else bars[-limit:]

    async def aclose(self) -> None:
        return None
