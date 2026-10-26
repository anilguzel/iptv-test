"""Leakage-safe weekly feature panel.

For every (symbol, week t) row the features use ONLY data up to the close of
week t, and the target is the NEXT week's return in excess of the benchmark.
Returns are measured between consecutive weeks of the trading calendar (the
union of weeks any symbol traded), so a full holiday week does not break them.

Features are z-scored across the symbols of the same week, which makes them
comparable between stocks and strips the market-wide drift (important for BIST,
where nominal TL prices are inflated over multi-year windows). The training
target is the cross-sectional rank of the next-week excess return.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .weekly import WeekKey, WeeklyBar

FEATURE_NAMES: list[str] = [
    "ex_ret_1w",           # last week's excess return
    "ex_ret_4w",           # 4-week excess return
    "ex_ret_12w",          # 12-week excess return (momentum)
    "vol_4w",              # 4-week volatility of weekly returns
    "vol_12w",             # 12-week volatility
    "log_volume_ratio",    # this week's volume vs the previous 12 weeks
    "dist_from_12w_high",  # close vs the 12-week high
    "range_1w",            # (high - low) / close this week
]
LOOKBACK = 12
# The benchmark must cover this share of the calendar, otherwise we fall back
# to the equal-weighted universe average.
MIN_BENCHMARK_COVERAGE = 0.8


@dataclass
class Panel:
    feature_names: list[str]
    calendar: list[WeekKey]
    week_end: list[str]      # ISO date of each calendar week's last trading day
    X: np.ndarray            # (n, k) cross-sectionally z-scored features
    X_raw: np.ndarray        # (n, k) raw features
    week: np.ndarray         # (n,) calendar index of each row
    symbols: np.ndarray      # (n,) symbol of each row
    y_raw: np.ndarray        # (n,) next-week excess return, NaN if unknown
    y_rank: np.ndarray       # (n,) per-week rank of y_raw in [-0.5, 0.5], NaN if unknown
    benchmark: str           # benchmark actually used


def _series(weekly: list[WeeklyBar], index: dict[WeekKey, int], length: int) -> dict[str, np.ndarray]:
    out = {k: np.full(length, np.nan) for k in ("close", "high", "low", "volume")}
    for b in weekly:
        i = index.get(b.week)
        if i is None:
            continue
        out["close"][i] = b.close
        out["high"][i] = b.high
        out["low"][i] = b.low
        out["volume"][i] = b.volume
    return out


def _returns(close: np.ndarray) -> np.ndarray:
    ret = np.full(close.shape, np.nan)
    ret[1:] = close[1:] / close[:-1] - 1
    return ret


def _zscore(values: np.ndarray) -> np.ndarray:
    mu = values.mean(axis=0)
    sd = values.std(axis=0)
    flat = sd < 1e-12
    z = (values - mu) / np.where(flat, 1.0, sd)
    z[:, flat] = 0.0  # a constant column carries no cross-sectional information
    return z


def build_panel(
    weekly_by_symbol: dict[str, list[WeeklyBar]],
    benchmark_weekly: list[WeeklyBar] | None = None,
    *,
    benchmark_name: str = "XU100",
) -> Panel:
    calendar = sorted({b.week for bars in weekly_by_symbol.values() for b in bars})
    index = {wk: i for i, wk in enumerate(calendar)}
    T = len(calendar)

    end_dates = [""] * T
    for bars in weekly_by_symbol.values():
        for b in bars:
            i = index[b.week]
            iso = b.end_date.isoformat()
            if iso > end_dates[i]:
                end_dates[i] = iso

    symbols = sorted(weekly_by_symbol)
    series = {s: _series(weekly_by_symbol[s], index, T) for s in symbols}
    rets = {s: _returns(series[s]["close"]) for s in symbols}

    # Benchmark weekly returns on the same calendar.
    bench = np.full(T, np.nan)
    used = "universe_ew"
    if benchmark_weekly:
        bclose = _series(benchmark_weekly, index, T)["close"]
        bret = _returns(bclose)
        if T > 1 and np.isfinite(bret[1:]).mean() >= MIN_BENCHMARK_COVERAGE:
            bench, used = bret, benchmark_name
    if used == "universe_ew":
        stacked = np.vstack([rets[s] for s in symbols]) if symbols else np.empty((0, T))
        counts = np.isfinite(stacked).sum(axis=0)
        sums = np.nansum(stacked, axis=0)
        bench = np.where(counts >= 3, sums / np.maximum(counts, 1), np.nan)

    rows_x: list[list[float]] = []
    rows_w: list[int] = []
    rows_s: list[str] = []
    rows_y: list[float] = []
    for s in symbols:
        c, h, lo, v = (series[s][k] for k in ("close", "high", "low", "volume"))
        ex = rets[s] - bench
        for i in range(LOOKBACK, T):
            win = slice(i - LOOKBACK + 1, i + 1)  # weeks i-11 .. i
            if not (np.isfinite(ex[win]).all() and np.isfinite(c[win]).all()
                    and np.isfinite(h[win]).all() and np.isfinite(lo[win]).all()):
                continue
            base_vol = v[i - LOOKBACK:i]  # weeks i-12 .. i-1
            if not (np.isfinite(base_vol).all() and np.isfinite(v[i]) and base_vol.mean() > 0 and v[i] > 0):
                continue
            feats = [
                ex[i],
                ex[i - 3:i + 1].sum(),
                ex[win].sum(),
                rets[s][i - 3:i + 1].std(),
                rets[s][win].std(),
                float(np.log(v[i] / base_vol.mean())),
                c[i] / h[win].max() - 1,
                (h[i] - lo[i]) / c[i],
            ]
            target = ex[i + 1] if i + 1 < T else np.nan  # next week's excess return
            rows_x.append(feats)
            rows_w.append(i)
            rows_s.append(s)
            rows_y.append(float(target) if np.isfinite(target) else np.nan)

    k = len(FEATURE_NAMES)
    X_raw = np.array(rows_x, dtype=float).reshape(-1, k)
    week = np.array(rows_w, dtype=int)
    y_raw = np.array(rows_y, dtype=float)
    X = np.zeros_like(X_raw)
    y_rank = np.full(len(y_raw), np.nan)
    for i in np.unique(week):
        m = week == i
        X[m] = _zscore(X_raw[m])
        known = m & np.isfinite(y_raw)
        n_known = int(known.sum())
        if n_known >= 2:
            order = y_raw[known].argsort().argsort()
            y_rank[known] = order / (n_known - 1) - 0.5
        elif n_known == 1:
            y_rank[known] = 0.0

    return Panel(
        feature_names=list(FEATURE_NAMES),
        calendar=calendar,
        week_end=end_dates,
        X=X,
        X_raw=X_raw,
        week=week,
        symbols=np.array(rows_s, dtype=object),
        y_raw=y_raw,
        y_rank=y_rank,
        benchmark=used,
    )
