from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest
from bist_core.research.features import build_panel
from bist_core.research.models import RidgeRanker
from bist_core.research.report import run_research
from bist_core.research.synthetic import synthetic_universe
from bist_core.research.walkforward import (
    HoldoutLockedError,
    WalkForwardConfig,
    eval_weeks,
    run_strategy,
)
from bist_core.research.weekly import to_weekly
from bist_core.schemas import OhlcvBar

CFG = WalkForwardConfig(top_n=4, min_train_weeks=40, holdout_weeks=10)


def _bar(day: int, close: float | None, *, high=None, low=None, vol=100.0) -> OhlcvBar:
    c = close if close is not None else 0.0
    return OhlcvBar(
        symbol="X",
        timestamp=datetime(2024, 1, day, 15, tzinfo=UTC),  # Jan 1 2024 is a Monday
        open=c, high=high or c, low=low or c, close=c, volume=vol,
    )


def _weekly(daily: dict) -> dict:
    return {s: to_weekly(b) for s, b in daily.items()}


# -- weekly resampling -------------------------------------------------------- #
def test_to_weekly_aggregates_a_week():
    days = [_bar(1, 10, high=11), _bar(2, 12, low=9), _bar(3, 11), _bar(4, 13, high=14), _bar(5, 12)]
    (w,) = to_weekly(days)
    assert (w.open, w.close, w.high, w.low) == (10, 12, 14, 9)
    assert w.volume == 500 and w.n_days == 5
    assert w.end_date.isoformat() == "2024-01-05"


def test_to_weekly_drops_unclosed_bars():
    weeks = to_weekly([_bar(1, 10), _bar(2, None)])  # close null -> not closed yet
    assert weeks[0].close == 10 and weeks[0].n_days == 1


# -- leakage ------------------------------------------------------------------- #
def test_features_at_week_t_ignore_all_later_data():
    """Rows for week t must be identical whether or not the future exists."""
    daily, bench = synthetic_universe(n_stocks=12, n_weeks=60, momentum=0.5, seed=3)
    full = build_panel(_weekly(daily), to_weekly(bench))
    t = 40
    cutoff = full.week_end[t]
    cut = {s: [b for b in bars if b.timestamp.date().isoformat() <= cutoff] for s, bars in daily.items()}
    cut_bench = [b for b in bench if b.timestamp.date().isoformat() <= cutoff]
    truncated = build_panel(_weekly(cut), to_weekly(cut_bench))

    wk = full.calendar[t]
    rows_full = {s: i for i, s in enumerate(full.symbols) if full.week[i] == t}
    t_cut = truncated.calendar.index(wk)
    rows_cut = {s: i for i, s in enumerate(truncated.symbols) if truncated.week[i] == t_cut}
    assert rows_full.keys() == rows_cut.keys() and rows_full
    for s, i in rows_full.items():
        j = rows_cut[s]
        np.testing.assert_allclose(full.X_raw[i], truncated.X_raw[j])
        np.testing.assert_allclose(full.X[i], truncated.X[j])
        assert np.isnan(truncated.y_raw[j])  # target is the unknown future


def test_walk_forward_never_trains_on_the_future():
    daily, bench = synthetic_universe(n_stocks=16, n_weeks=120, momentum=0.5, seed=5)
    panel = build_panel(_weekly(daily), to_weekly(bench))
    res = run_strategy(panel, RidgeRanker(), eval_weeks(panel, CFG), CFG)
    assert res.steps
    for step in res.steps:
        assert step.train_max_week < step.week


# -- known-answer validation -------------------------------------------------- #
def test_pure_noise_finds_no_edge():
    daily, bench = synthetic_universe(n_stocks=20, n_weeks=140, momentum=0.0, seed=11)
    report = run_research(daily, bench, CFG)
    ridge = report["strategies"]["ridge"]["metrics"]
    assert abs(ridge["mean_ic"]) < 0.06
    assert report["verdict"]["models"]["ridge"]["passed"] is False


def test_planted_signal_is_found():
    daily, bench = synthetic_universe(n_stocks=20, n_weeks=140, momentum=0.5, seed=11)
    report = run_research(daily, bench, CFG)
    ridge = report["strategies"]["ridge"]["metrics"]
    assert ridge["mean_ic"] > 0.15
    assert ridge["ic_tstat"] > 2
    # The planted signal *is* 4-week momentum, so that baseline is the oracle
    # here; the strategy selection must find it (or the model) with confidence.
    st = report["strategy"]
    assert st["chosen"] in {"momentum_4w", "ridge"} and st["confidence"] == "GÜÇLÜ"
    assert st["holdout"]["mean_weekly_net"] > 0 and len(st["next_week"]["picks"]) == CFG.top_n
    # The model should have learned that recent excess return predicts next week.
    assert report["next_week"]["coefficients"]["ex_ret_4w"] > 0
    assert len(report["next_week"]["picks"]) == CFG.top_n


# -- safety rails --------------------------------------------------------------- #
def test_holdout_is_locked_by_default():
    daily, bench = synthetic_universe(n_stocks=12, n_weeks=120, seed=2)
    panel = build_panel(_weekly(daily), to_weekly(bench))
    locked = WalkForwardConfig(top_n=4, min_train_weeks=40, holdout_weeks=10, segment="holdout")
    with pytest.raises(HoldoutLockedError):
        eval_weeks(panel, locked)
    unlocked = WalkForwardConfig(top_n=4, min_train_weeks=40, holdout_weeks=10, segment="holdout", unlock_holdout=True)
    assert len(eval_weeks(panel, unlocked)) == 10


def test_holdout_weeks_are_excluded_from_validation():
    daily, bench = synthetic_universe(n_stocks=12, n_weeks=120, seed=2)
    panel = build_panel(_weekly(daily), to_weekly(bench))
    validation = eval_weeks(panel, CFG)
    holdout = eval_weeks(panel, WalkForwardConfig(**{**CFG.__dict__, "segment": "holdout", "unlock_holdout": True}))
    assert not set(validation) & set(holdout)
    assert max(validation) < min(holdout)


def test_too_little_history_is_rejected():
    daily, bench = synthetic_universe(n_stocks=12, n_weeks=50, seed=2)
    panel = build_panel(_weekly(daily), to_weekly(bench))
    with pytest.raises(ValueError, match="Not enough history"):
        eval_weeks(panel, CFG)


def test_missing_benchmark_falls_back_to_universe_average():
    daily, _ = synthetic_universe(n_stocks=12, n_weeks=40, seed=2)
    assert build_panel(_weekly(daily), None).benchmark == "universe_ew"


def test_strategy_selection_rarely_claims_strength_on_noise():
    strong = 0
    for seed in range(20):
        daily, bench = synthetic_universe(n_stocks=20, n_weeks=200, momentum=0.0, seed=seed)
        st = run_research(daily, bench, CFG)["strategy"]
        assert st["confidence"] in {"GÜÇLÜ", "ORTA", "ZAYIF", "YOK"}
        assert "random" not in [c["strategy"] for c in st["candidates"]]  # random is the control
        strong += st["confidence"] == "GÜÇLÜ"
    assert strong <= 2


def test_strategy_selection_without_eligible_candidate_says_hold_the_index():
    from bist_core.research.selection import select_strategy
    from bist_core.research.walkforward import StrategyResult

    losing = StrategyResult(name="momentum_12w", steps=[], metrics={})
    losing.steps = [type("S", (), {"net": -0.01, "hold_week_end": "2026-01-02"})() for _ in range(10)]
    st = select_strategy(type("P", (), {"benchmark": "XU100"})(), {"momentum_12w": losing}, {}, CFG)
    assert st["chosen"] is None and st["confidence"] == "YOK" and "endeksini tut" in st["summary_tr"]


def test_forecast_rows_calibration_and_track_record():
    from bist_core.research.forecast import forecast_csv, history_csv

    daily, bench = synthetic_universe(n_stocks=20, n_weeks=200, momentum=0.5, seed=3)
    fc = run_research(daily, bench, CFG)["forecast"]
    assert len(fc["stocks"]) == 20 and sum(s["pick"] for s in fc["stocks"]) == CFG.top_n
    assert [s["rank"] for s in fc["stocks"]] == list(range(1, 21))
    cal = fc["calibration"]
    # planted momentum: the top-scored fifth must do better than the bottom fifth
    assert cal[-1]["mean_excess"] > cal[0]["mean_excess"]
    assert cal[-1]["beat_benchmark_probability"] > 0.5
    # each stock gets its own expectation, falling with its rank on a planted signal
    exp = [s["expected_excess"] for s in fc["stocks"]]
    assert len(set(exp)) == len(exp) and exp == sorted(exp, reverse=True)
    assert fc["track_record"]["weeks"] == len(fc["history"]) > 100
    assert all(h["signal_week_end"] < (h["hold_week_end"] or "9") for h in fc["history"])
    assert forecast_csv(fc).count("\n") == 21 and "EVET" in history_csv(fc)


def test_fx_feature_and_rule_when_usdtry_is_given():
    from bist_core.research.features import FEATURE_NAMES, build_panel

    daily, bench = synthetic_universe(n_stocks=12, n_weeks=140, seed=5)
    # A stand-in USD/TRY series (the benchmark path) is enough to exercise the plumbing.
    fx = [b.model_copy(update={"symbol": "TP.DK.USD.A"}) for b in bench]
    weekly = _weekly(daily)
    with_fx = build_panel(weekly, to_weekly(bench), fx_weekly=to_weekly(fx))
    without = build_panel(weekly, to_weekly(bench))
    k = FEATURE_NAMES.index("fx_beta_x_trend")
    assert np.any(with_fx.X_raw[:, k] != 0) and np.all(without.X_raw[:, k] == 0)

    report = run_research(daily, bench, CFG, fx_daily=fx)
    assert "fx_tilt" in report["strategies"]
    assert "fx_tilt" not in run_research(daily, bench, CFG)["strategies"]


def test_boosting_learns_a_planted_signal_and_retrains_for_the_forecast():
    from bist_core.research.models import BoostedRanker

    daily, bench = synthetic_universe(n_stocks=20, n_weeks=200, momentum=0.5, seed=3)
    report = run_research(daily, bench, CFG)
    m = report["strategies"]["boosting"]["metrics"]
    assert m["mean_ic"] > 0.1 and m["ic_tstat"] > 2
    # never trained on its own test week
    steps = report["strategies"]["boosting"]["steps"]
    assert all(s["train_max_week"] < s["week"] for s in steps)

    b = BoostedRanker(refit_every=4)
    X, y = np.random.default_rng(0).standard_normal((400, 9)), np.random.default_rng(1).standard_normal(400)
    b.fit(X, y)
    first = b._model
    b.fit(X, y)  # within the refit window: model kept
    assert b._model is first
    b.reset()
    b.fit(X, y)  # after reset: always retrained
    assert b._model is not first
