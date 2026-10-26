from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bist_core.config import Settings
from bist_core.engines import performance as perf
from bist_core.scoring_config import (
    DEFAULT_WEIGHTS,
    load_weights,
    scoring_config_from_settings,
)

T0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)


def _two_point(ret: float) -> list[perf.PricePoint]:
    # entry 10 at T0, exit at T0+30m giving the requested raw return.
    return [
        perf.PricePoint(timestamp=T0, price=10.0),
        perf.PricePoint(timestamp=T0 + timedelta(minutes=30), price=10.0 * (1 + ret)),
    ]


def _dataset():
    rets = {"A": 0.10, "B": 0.05, "C": -0.05, "D": -0.10}
    pm_norm = {"A": 0.9, "B": 0.7, "C": 0.3, "D": 0.1}  # tracks the return
    scores = {"A": 80, "B": 65, "C": 65, "D": 80}
    signals = [
        perf.SignalRecord(
            symbol=sym,
            timestamp=T0,
            score=scores[sym],
            direction="POSITIVE",
            component_norms={"price_momentum": pm_norm[sym], "news": 0.5},
        )
        for sym in rets
    ]
    prices = {sym: _two_point(r) for sym, r in rets.items()}
    return signals, prices


def test_analyze_basic_stats():
    signals, prices = _dataset()
    report = perf.analyze(signals, prices, horizon_min=30)
    assert report.evaluated == 4
    assert report.overall_win_rate == 0.5  # two up, two down
    assert abs(report.overall_avg_return) < 1e-9  # +0.10 +0.05 -0.05 -0.10 = 0
    assert report.by_direction["POSITIVE"]["count"] == 4
    assert set(report.by_band) == {"STRONG_POSITIVE", "POSITIVE"}


def test_component_correlation_detects_predictive_component():
    signals, prices = _dataset()
    report = perf.analyze(signals, prices, horizon_min=30)
    # price_momentum norm tracks the return -> strong positive correlation.
    assert report.component_correlations["price_momentum"] > 0.9
    # news norm is constant (zero variance) -> excluded, never fabricated.
    assert "news" not in report.component_correlations


def test_propose_weights_tilts_and_renormalises():
    proposed = perf.propose_weights(DEFAULT_WEIGHTS, {"price_momentum": 0.95}, aggressiveness=0.5)
    assert abs(sum(proposed.values()) - 100.0) < 0.01  # 4-dp rounding noise
    # The predictive component gains share; an untouched one loses share.
    assert proposed["price_momentum"] > DEFAULT_WEIGHTS["price_momentum"]
    assert proposed["news"] < DEFAULT_WEIGHTS["news"]


def test_no_forward_prices_yields_zero_evaluated():
    signals, _ = _dataset()
    report = perf.analyze(signals, {}, horizon_min=30)
    assert report.evaluated == 0
    assert report.overall_win_rate == 0.0


# -- scoring weight overrides ------------------------------------------------ #
def test_load_weights_default_when_absent():
    assert load_weights(None) == DEFAULT_WEIGHTS
    assert load_weights("not json") == DEFAULT_WEIGHTS


def test_load_weights_renormalises_to_100():
    w = load_weights('{"price_momentum": 30, "volume": 30, "technical": 40, "news": 0}')
    assert abs(sum(w.values()) - 100.0) < 1e-6


def test_scoring_config_from_settings_applies_override():
    cfg = scoring_config_from_settings(Settings(SCORING_WEIGHTS='{"price_momentum": 40}'))
    assert abs(sum(cfg.weights.values()) - 100.0) < 1e-6
    # 40 before renormalisation is the largest raw weight -> largest share.
    assert cfg.weights["price_momentum"] == max(cfg.weights.values())
