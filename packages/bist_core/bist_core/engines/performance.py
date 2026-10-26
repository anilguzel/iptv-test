"""Signal-performance analysis + strategy (weight) calibration.

Scans historical signals, measures how well they worked (win rate / return by
direction and by score band), and estimates how predictive each scoring
component was (correlation of its normalised value with the forward return).

From those correlations it can *propose* adjusted scoring weights. This is an
offline, opt-in calibration aid — per the spec, the learning loop never mutates
production thresholds automatically. The proposal is applied deliberately via
the ``SCORING_WEIGHTS`` setting.

Look-ahead bias is prevented exactly as in the backtest engine: entry is the
last price known AT the signal, forward prices are strictly after it.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .backtest import _direction_sign  # signed direction (+1 long / -1 short / 0)

# Score bands mirror the direction thresholds.
BANDS: list[tuple[float, float, str]] = [
    (0, 25, "STRONG_NEGATIVE"),
    (25, 40, "NEGATIVE"),
    (40, 60, "NEUTRAL"),
    (60, 75, "POSITIVE"),
    (75, 90, "STRONG_POSITIVE"),
    (90, 100.01, "EXTREME_POSITIVE"),
]


@dataclass
class SignalRecord:
    symbol: str
    timestamp: datetime
    score: float
    direction: str
    component_norms: dict[str, float] = field(default_factory=dict)


@dataclass
class PricePoint:
    timestamp: datetime
    price: float


def _forward_return(prices: list[PricePoint], at: datetime, horizon_min: int) -> float | None:
    """Raw (unsigned) forward return over `horizon_min`, look-ahead-safe."""
    prices = sorted(prices, key=lambda p: p.timestamp)
    known = [p for p in prices if p.timestamp <= at]
    if not known:
        return None
    entry = known[-1].price
    if entry <= 0:
        return None
    cutoff = at + timedelta(minutes=horizon_min)
    window = [p for p in prices if at < p.timestamp <= cutoff]
    if not window:
        return None
    return (window[-1].price - entry) / entry


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    try:
        return statistics.correlation(xs, ys)
    except (statistics.StatisticsError, ValueError):
        return None  # zero variance etc.


@dataclass
class PerformanceReport:
    horizon_min: int
    total_signals: int
    evaluated: int
    overall_win_rate: float
    overall_avg_return: float
    by_direction: dict[str, dict]
    by_band: dict[str, dict]
    component_correlations: dict[str, float]


def analyze(
    signals: list[SignalRecord],
    prices_by_symbol: dict[str, list[PricePoint]],
    *,
    horizon_min: int = 30,
) -> PerformanceReport:
    rows: list[tuple[SignalRecord, float, float]] = []  # (record, raw_return, signed_return)
    for sig in signals:
        raw = _forward_return(prices_by_symbol.get(sig.symbol, []), sig.timestamp, horizon_min)
        if raw is None:
            continue
        signed = raw * _direction_sign(sig.direction)
        rows.append((sig, raw, signed))

    evaluated = len(rows)
    # Direction-traded rows only (exclude NEUTRAL/WATCH) for win/return stats.
    traded = [(s, raw, signed) for (s, raw, signed) in rows if _direction_sign(s.direction) != 0]
    signed_returns = [signed for (_s, _raw, signed) in traded]
    overall_win = (sum(1 for r in signed_returns if r > 0) / len(signed_returns)) if signed_returns else 0.0
    overall_avg = statistics.fmean(signed_returns) if signed_returns else 0.0

    def _stats(subset: list[float]) -> dict:
        if not subset:
            return {"count": 0, "win_rate": 0.0, "avg_return": 0.0}
        return {
            "count": len(subset),
            "win_rate": round(sum(1 for r in subset if r > 0) / len(subset), 4),
            "avg_return": round(statistics.fmean(subset), 6),
        }

    by_direction: dict[str, dict] = {}
    for direction in {s.direction for (s, _r, _sg) in traded}:
        subset = [sg for (s, _r, sg) in traded if s.direction == direction]
        by_direction[direction] = _stats(subset)

    by_band: dict[str, dict] = {}
    for lo, hi, label in BANDS:
        subset = [sg for (s, _r, sg) in traded if lo <= s.score < hi]
        if subset:
            by_band[label] = _stats(subset)

    # Component predictiveness: correlate each component norm with RAW return
    # (norms are directional, so positive correlation => the component helped).
    component_keys: set[str] = set()
    for s, _r, _sg in rows:
        component_keys.update(s.component_norms.keys())
    correlations: dict[str, float] = {}
    for key in sorted(component_keys):
        xs, ys = [], []
        for s, raw, _sg in rows:
            if key in s.component_norms:
                xs.append(s.component_norms[key])
                ys.append(raw)
        corr = _pearson(xs, ys)
        if corr is not None:
            correlations[key] = round(corr, 4)

    return PerformanceReport(
        horizon_min=horizon_min,
        total_signals=len(signals),
        evaluated=evaluated,
        overall_win_rate=round(overall_win, 4),
        overall_avg_return=round(overall_avg, 6),
        by_direction=by_direction,
        by_band=by_band,
        component_correlations=correlations,
    )


def propose_weights(
    current_weights: dict[str, float],
    correlations: dict[str, float],
    *,
    aggressiveness: float = 0.5,
) -> dict[str, float]:
    """Tilt weights toward components that correlated with returns.

    new_w_i = current_w_i * (1 + aggressiveness * corr_i), floored at 10% of the
    original to avoid zeroing a component, then renormalised to sum to 100.
    A component with no measured correlation is left unchanged.
    """
    adjusted: dict[str, float] = {}
    for name, w in current_weights.items():
        corr = correlations.get(name, 0.0)
        factor = max(0.1, 1 + aggressiveness * corr)
        adjusted[name] = w * factor
    total = sum(adjusted.values())
    if total <= 0:
        return dict(current_weights)
    return {name: round(w / total * 100, 4) for name, w in adjusted.items()}
