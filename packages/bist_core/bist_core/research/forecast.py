"""Turn a strategy into forecast data: one row per stock for next week, plus
the record of every past week's forecast against what actually happened.

Each week the strategy scores every stock using only data up to that week.
Stocks are split into five groups (quintiles) by score. Over all past weeks
we measure, per group, the average next-week excess return and how often it
beat the benchmark. That calibration turns this week's scores into numbers:
"expected excess return" and "probability of beating the benchmark".
"""
from __future__ import annotations

import numpy as np

from .features import Panel

N_GROUPS = 5


def _groups(scores: np.ndarray) -> np.ndarray:
    """0 = lowest-scored fifth ... 4 = highest-scored fifth."""
    ranks = scores.argsort(kind="stable").argsort(kind="stable")
    return np.minimum(ranks * N_GROUPS // max(len(scores), 1), N_GROUPS - 1)


def build_forecast(panel: Panel, strategy, weeks: list[int], top_n: int) -> dict:
    """Walk forward over ``weeks`` (training only on earlier weeks), then score the latest week."""
    has_target = np.isfinite(panel.y_rank)
    history: list[dict] = []
    group_returns: list[list[float]] = [[] for _ in range(N_GROUPS)]
    for t in weeks:
        if strategy.trains:
            strategy.fit(panel.X[(panel.week < t) & has_target], panel.y_rank[(panel.week < t) & has_target])
        rows = (panel.week == t) & np.isfinite(panel.y_raw)
        if rows.sum() < N_GROUPS:
            continue
        scores = strategy.predict(panel.X[rows])
        outcome = panel.y_raw[rows]
        syms = panel.symbols[rows]
        groups = _groups(scores)
        for g, r in zip(groups, outcome, strict=True):
            group_returns[int(g)].append(float(r))
        top = np.argsort(-scores, kind="stable")[:top_n]
        hit = float((outcome[top] > 0).mean())
        history.append({
            "signal_week_end": panel.week_end[t],
            "hold_week_end": panel.week_end[t + 1] if t + 1 < len(panel.week_end) else None,
            "picks": [str(s) for s in syms[top]],
            "picks_excess": round(float(outcome[top].mean()), 6),
            "picks_beat_benchmark_share": round(hit, 4),
            "all_stocks_excess": round(float(outcome.mean()), 6),
        })

    calibration = []
    for g, rets in enumerate(group_returns):
        arr = np.array(rets)
        calibration.append({
            "group": g + 1,
            "observations": len(arr),
            "mean_excess": round(float(arr.mean()), 6) if len(arr) else None,
            "beat_benchmark_probability": round(float((arr > 0).mean()), 4) if len(arr) else None,
        })

    latest = int(panel.week.max())
    if hasattr(strategy, "reset"):
        strategy.reset()  # the final forecast always uses a model trained on every known week
    if strategy.trains:
        strategy.fit(panel.X[has_target], panel.y_rank[has_target])
    rows = panel.week == latest
    scores = strategy.predict(panel.X[rows])
    syms = panel.symbols[rows]
    groups = _groups(scores) if len(scores) >= N_GROUPS else np.full(len(scores), N_GROUPS // 2)
    order = np.argsort(-scores, kind="stable")
    stocks = []
    for rank, i in enumerate(order, start=1):
        cal = calibration[int(groups[i])]
        stocks.append({
            "rank": rank,
            "symbol": str(syms[i]),
            "score": round(float(scores[i]), 5),
            "group": int(groups[i]) + 1,
            "expected_excess": cal["mean_excess"],
            "beat_benchmark_probability": cal["beat_benchmark_probability"],
            "pick": rank <= top_n,
        })

    hits = [h["picks_excess"] > 0 for h in history]
    equity = np.cumprod([1 + h["picks_excess"] for h in history]) if history else np.array([1.0])
    return {
        "as_of_week_end": panel.week_end[latest],
        "benchmark": panel.benchmark,
        "stocks": stocks,
        "calibration": calibration,
        "history": history,
        "track_record": {
            "weeks": len(history),
            "weeks_picks_beat_benchmark": round(float(np.mean(hits)), 4) if hits else None,
            "mean_weekly_excess": round(float(np.mean([h["picks_excess"] for h in history])), 6) if history else None,
            "cumulative_excess_before_costs": round(float(equity[-1] - 1), 6),
        },
    }


def forecast_csv(forecast: dict) -> str:
    lines = ["rank,symbol,group,expected_excess_pct,beat_benchmark_probability_pct,pick"]
    for s in forecast["stocks"]:
        exp = "" if s["expected_excess"] is None else f"{s['expected_excess'] * 100:.2f}"
        prob = "" if s["beat_benchmark_probability"] is None else f"{s['beat_benchmark_probability'] * 100:.1f}"
        lines.append(f"{s['rank']},{s['symbol']},{s['group']},{exp},{prob},{'EVET' if s['pick'] else ''}")
    return "\n".join(lines) + "\n"


def history_csv(forecast: dict) -> str:
    lines = ["signal_week_end,hold_week_end,picks,picks_excess_pct,all_stocks_excess_pct,picks_beat_benchmark"]
    for h in forecast["history"]:
        lines.append(f"{h['signal_week_end']},{h['hold_week_end'] or ''},{' '.join(h['picks'])},"
                     f"{h['picks_excess'] * 100:.2f},{h['all_stocks_excess'] * 100:.2f},"
                     f"{'EVET' if h['picks_excess'] > 0 else 'HAYIR'}")
    return "\n".join(lines) + "\n"
