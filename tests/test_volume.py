from __future__ import annotations

from bist_core.engines.volume import VolumeEngine, baseline_from_history
from conftest import make_ticks


def test_volume_ratio_detects_spike():
    # Baseline ~1000/min. Last 5 min trades ~4.5x that.
    prices = [10.0] * 11
    volumes = [0.0, 1000, 2000, 3000, 4000, 5000, 5000 + 4500, 5000 + 9000, 5000 + 13500, 5000 + 18000, 5000 + 22500]
    ticks = make_ticks(prices, volumes)

    m = VolumeEngine().compute(ticks, baseline_per_minute=1000.0)
    assert m.volume_ratio_5m >= 3.0  # clears the VOLUME_SPIKE threshold


def test_no_baseline_is_neutral_not_fabricated():
    ticks = make_ticks([10.0, 10.0, 10.0], [0.0, 5000.0, 10000.0])
    m = VolumeEngine().compute(ticks, baseline_per_minute=None)
    assert m.volume_ratio_5m == 1.0  # neutral, never a fake spike


def test_baseline_from_history():
    # Avg daily 390_000 over a 390-min session -> 1000/min.
    assert baseline_from_history([390_000, 390_000, 390_000]) == 1000.0
    assert baseline_from_history([]) is None
