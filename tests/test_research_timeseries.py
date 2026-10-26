from __future__ import annotations

import numpy as np
import pytest
from bist_core.research.features import build_panel
from bist_core.research.report import run_timeseries_research
from bist_core.research.synthetic import synthetic_single, synthetic_universe
from bist_core.research.timeseries import (
    TSRidge,
    binomial_pvalue_greater,
    effective_n,
    run_ts_strategy,
)
from bist_core.research.walkforward import WalkForwardConfig, eval_weeks
from bist_core.research.weekly import to_weekly

CFG = WalkForwardConfig(min_train_weeks=52, holdout_weeks=26)


def _run(autocorr: float, seed: int, n_weeks: int = 300) -> dict:
    daily, bench = synthetic_single(n_weeks=n_weeks, autocorr=autocorr, seed=seed)
    (sym, bars), = daily.items()
    return run_timeseries_research(bars, sym, bench, CFG, benchmark_name="BENCH")


def test_pure_noise_single_stock_is_not_significant():
    report = _run(autocorr=0.0, seed=0)
    v = report["verdict"]["models"]["ridge"]
    assert v["checks"]["ic_significant"] is False
    assert v["passed"] is False


def test_strong_planted_autocorrelation_is_detected():
    report = _run(autocorr=0.6, seed=3)
    m = report["strategies"]["ridge"]["metrics"]
    assert m["mean_ic"] > 0.3
    assert report["verdict"]["models"]["ridge"]["passed"] is True
    nw = report["next_week"]
    assert nw["position"] in {"LONG", "FLAT"} and nw["symbol"] == "SYNTS"


def test_single_stock_never_trains_on_the_future():
    daily, bench = synthetic_single(n_weeks=160, autocorr=0.3, seed=1)
    (sym, bars), = daily.items()
    panel = build_panel({sym: to_weekly(bars)}, to_weekly(bench), fallback="none")
    res = run_ts_strategy(panel, TSRidge(), eval_weeks(panel, CFG, min_rows=1), CFG)
    assert res.steps
    assert all(s.train_max_week < s.week for s in res.steps)


def test_timeseries_requires_exactly_one_symbol():
    daily, bench = synthetic_universe(n_stocks=3, n_weeks=120, seed=1)
    panel = build_panel({s: to_weekly(b) for s, b in daily.items()}, to_weekly(bench))
    with pytest.raises(ValueError, match="exactly one symbol"):
        run_ts_strategy(panel, TSRidge(), [100], CFG)


def test_no_benchmark_single_stock_uses_raw_returns():
    daily, _ = synthetic_single(n_weeks=80, seed=1)
    (sym, bars), = daily.items()
    panel = build_panel({sym: to_weekly(bars)}, None, fallback="none")
    assert panel.benchmark == "none" and np.isfinite(panel.y_raw).any()


def test_effective_n_only_shrinks_when_both_series_are_autocorrelated():
    rng = np.random.default_rng(0)
    n = 300
    white_a, white_b = rng.standard_normal(n), rng.standard_normal(n)

    def ar1(phi: float) -> np.ndarray:
        x = np.zeros(n)
        for i in range(1, n):
            x[i] = phi * x[i - 1] + rng.standard_normal()
        return x

    smooth_a, smooth_b = ar1(0.9), ar1(0.9)
    assert effective_n(white_a, white_b) > 0.8 * n
    assert effective_n(smooth_a, white_b) > 0.8 * n  # one autocorrelated series is fine
    assert effective_n(smooth_a, smooth_b) < 0.4 * n


def test_binomial_pvalue():
    assert binomial_pvalue_greater(10, 10) == pytest.approx(0.5**10)
    assert binomial_pvalue_greater(0, 10) == pytest.approx(1.0)
    assert 0.4 < binomial_pvalue_greater(5, 10) < 0.7


def test_synthetic_single_rejects_unstable_process():
    with pytest.raises(ValueError):
        synthetic_single(autocorr=1.0)


def test_tactic_text_without_benchmark_says_raw_returns():
    daily, _ = synthetic_single(n_weeks=160, autocorr=0.0, seed=1)
    (sym, bars), = daily.items()
    report = run_timeseries_research(bars, sym, None, CFG)
    assert report["meta"]["benchmark_used"] == "none"
    assert "ham getiri" in report["tactic_tr"] and "(none)" not in report["tactic_tr"]
