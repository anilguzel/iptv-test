"""Volume analysis: rolling ratios vs a historical baseline + spike detection."""
from __future__ import annotations

from datetime import datetime, timedelta
from itertools import pairwise

from ..schemas import Tick, VolumeMetrics


def _increment_volume(ticks: list[Tick], end: datetime, minutes: float) -> float:
    """Volume traded in the last `minutes`, derived from cumulative volume."""
    lo = end - timedelta(minutes=minutes)
    window = [t for t in ticks if lo < t.timestamp <= end]
    if len(window) < 2:
        return 0.0
    total = 0.0
    for prev, cur in pairwise(window):
        dv = cur.volume - prev.volume
        total += dv if dv >= 0 else cur.volume
    return total


class VolumeEngine:
    """Computes volume ratios against a per-minute baseline.

    ``baseline_per_minute`` is the typical volume traded per minute for the
    symbol (from historical intraday data). When unknown, the ratio defaults to
    1.0 (neutral) rather than a fabricated spike.
    """

    def compute(self, ticks: list[Tick], *, baseline_per_minute: float | None) -> VolumeMetrics:
        ticks = sorted(ticks, key=lambda t: t.timestamp)
        if len(ticks) < 2:
            return VolumeMetrics()
        now = ticks[-1].timestamp

        vol_5m = _increment_volume(ticks, now, 5)
        vol_15m = _increment_volume(ticks, now, 15)
        vol_day = max(ticks[-1].volume - ticks[0].volume, 0.0)

        def ratio(window_vol: float, minutes: float) -> float:
            if not baseline_per_minute or baseline_per_minute <= 0:
                return 1.0
            expected = baseline_per_minute * minutes
            return round(window_vol / expected, 4) if expected else 1.0

        return VolumeMetrics(
            volume_ratio_5m=ratio(vol_5m, 5),
            volume_ratio_15m=ratio(vol_15m, 15),
            volume_ratio_day=ratio(vol_day, max((now - ticks[0].timestamp).total_seconds() / 60, 1)),
            volume_5m=vol_5m,
            volume_15m=vol_15m,
        )


def baseline_from_history(daily_volumes: list[float], session_minutes: int = 390) -> float | None:
    """Estimate per-minute baseline volume from recent daily volumes."""
    valid = [v for v in daily_volumes if v and v > 0]
    if not valid:
        return None
    avg_daily = sum(valid) / len(valid)
    return avg_daily / session_minutes
