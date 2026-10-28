"""Walk-forward evaluation.

For each test week t:
  1. train on rows whose target is already known at the close of week t
     (feature week < t, so the target week <= t: nothing from the future),
  2. score every stock using week t's features,
  3. "hold" the top-N stocks for week t+1 and record their realised excess
     return (net of trading costs), the long-short spread and the rank IC,
  4. move one week forward and repeat.

The last ``holdout_weeks`` are locked away and only evaluated on explicit
request, so tuning can't quietly overfit them.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .features import Panel
from .models import MODEL_NAMES

ROLLING_WINDOW = 13  # ~one quarter, for the consistency score


class HoldoutLockedError(PermissionError):
    pass


@dataclass
class WalkForwardConfig:
    top_n: int = 5
    min_train_weeks: int = 52
    holdout_weeks: int = 26
    cost_bps_per_side: float = 10.0
    segment: str = "validation"  # "validation" or "holdout"
    unlock_holdout: bool = False


@dataclass
class Step:
    week: int                # calendar index of the signal week
    signal_week_end: str
    hold_week_end: str
    train_max_week: int      # last feature week used in training (must be < week)
    n_train: int
    top: list[str]
    gross: float             # mean next-week excess return of the top-N
    net: float               # after trading costs
    long_short: float        # top-N minus bottom-N
    ic: float | None         # Spearman rank correlation of scores vs outcomes
    turnover: float


@dataclass
class StrategyResult:
    name: str
    steps: list[Step] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _rank(a: np.ndarray) -> np.ndarray:
    return a.argsort(kind="stable").argsort(kind="stable").astype(float)


def spearman(a: np.ndarray, b: np.ndarray) -> float | None:
    if len(a) < 3:
        return None
    ra, rb = _rank(a), _rank(b)
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def eval_weeks(panel: Panel, cfg: WalkForwardConfig, *, min_rows: int | None = None) -> list[int]:
    """Weeks to evaluate, honouring min training history and the locked holdout.

    ``min_rows`` is the number of stocks a week needs to be usable: 2 x top_n
    for cross-sectional ranking (default), 1 for a single-stock time series.
    """
    min_rows = 2 * cfg.top_n if min_rows is None else min_rows
    known = np.isfinite(panel.y_raw)
    counts = {int(w): int(c) for w, c in zip(*np.unique(panel.week[known], return_counts=True), strict=True)}
    usable = sorted(w for w, c in counts.items() if c >= min_rows)
    needed = cfg.min_train_weeks + cfg.holdout_weeks + 1
    if len(usable) < needed:
        raise ValueError(
            f"Not enough history: {len(usable)} usable weeks, need at least {needed} "
            f"(min_train_weeks={cfg.min_train_weeks} + holdout_weeks={cfg.holdout_weeks} + 1)."
        )
    eligible = usable[cfg.min_train_weeks:]
    if cfg.holdout_weeks:
        validation, holdout = eligible[:-cfg.holdout_weeks], eligible[-cfg.holdout_weeks:]
    else:
        validation, holdout = eligible, []
    if cfg.segment == "holdout":
        if not cfg.unlock_holdout:
            raise HoldoutLockedError("The holdout is locked. Pass unlock_holdout=True once you are done tuning.")
        return holdout
    return validation


def run_strategy(panel: Panel, strategy, weeks: list[int], cfg: WalkForwardConfig) -> StrategyResult:
    result = StrategyResult(name=strategy.name)
    has_target = np.isfinite(panel.y_rank)
    prev_top: set[str] | None = None
    cost_per_turnover = 2 * cfg.cost_bps_per_side / 1e4  # sell old + buy new

    for t in weeks:
        train = (panel.week < t) & has_target
        if strategy.trains:
            strategy.fit(panel.X[train], panel.y_rank[train])
        test = (panel.week == t) & np.isfinite(panel.y_raw)
        scores = strategy.predict(panel.X[test])
        syms = panel.symbols[test]
        outcome = panel.y_raw[test]

        order = np.argsort(-scores, kind="stable")
        n = cfg.top_n
        top, bottom = order[:n], order[-n:]
        top_set = {str(s) for s in syms[top]}
        turnover = 1.0 if prev_top is None else 1 - len(top_set & prev_top) / n
        gross = float(outcome[top].mean())
        net = gross - turnover * cost_per_turnover
        prev_top = top_set

        hold_idx = t + 1 if t + 1 < len(panel.week_end) else t
        result.steps.append(
            Step(
                week=int(t),
                signal_week_end=panel.week_end[t],
                hold_week_end=panel.week_end[hold_idx],
                train_max_week=int(panel.week[train].max()) if train.any() else -1,
                n_train=int(train.sum()),
                top=sorted(top_set),
                gross=gross,
                net=net,
                long_short=float(outcome[top].mean() - outcome[bottom].mean()),
                ic=spearman(scores, outcome),
                turnover=turnover,
            )
        )
    result.metrics = compute_metrics(result.steps)
    return result


def return_stats(net: np.ndarray, hold_week_ends: list[str]) -> dict:
    """Return/risk statistics of a weekly net-return series (shared by both modes)."""
    equity = np.cumprod(1 + net)
    drawdown = equity / np.maximum.accumulate(equity) - 1
    sd = net.std(ddof=1) if len(net) > 1 else 0.0
    consistency = None
    if len(net) >= ROLLING_WINDOW:
        windows = np.convolve(net, np.ones(ROLLING_WINDOW), mode="valid")
        consistency = round(float((windows > 0).mean()), 4)

    per_year: dict[str, list[float]] = {}
    for d, r in zip(hold_week_ends, net, strict=True):
        per_year.setdefault(d[:4], []).append(float(r))
    per_year_stats = {
        y: {"weeks": len(v), "mean_net": round(float(np.mean(v)), 6), "cum_net": round(float(np.prod(1 + np.array(v)) - 1), 6)}
        for y, v in sorted(per_year.items())
    }
    return {
        "weeks": len(net),
        "mean_weekly_net": round(float(net.mean()), 6),
        "sharpe_annualised": round(float(net.mean() / sd * np.sqrt(52)), 3) if sd > 0 else None,
        "cumulative_net": round(float(equity[-1] - 1), 6),
        "max_drawdown": round(float(drawdown.min()), 6),
        "consistency_13w": consistency,
        "per_year": per_year_stats,
    }


def compute_metrics(steps: list[Step]) -> dict:
    if not steps:
        return {"weeks": 0}
    net = np.array([s.net for s in steps])
    ics = np.array([s.ic for s in steps if s.ic is not None])
    ic_sd = ics.std(ddof=1) if len(ics) > 1 else 0.0
    return {
        **return_stats(net, [s.hold_week_end for s in steps]),
        "hit_rate": round(float((net > 0).mean()), 4),
        "mean_ic": round(float(ics.mean()), 4) if len(ics) else None,
        "ic_tstat": round(float(ics.mean() / (ic_sd / np.sqrt(len(ics)))), 3) if ic_sd > 0 else None,
        "ic_hit_rate": round(float((ics > 0).mean()), 4) if len(ics) else None,
        "mean_long_short": round(float(np.mean([s.long_short for s in steps])), 6),
        "mean_turnover": round(float(np.mean([s.turnover for s in steps])), 4),
    }


# Pass criteria for a model to count as a consistent tactic.
MIN_IC_TSTAT = 2.0
MIN_CONSISTENCY = 0.6


def verdict(results: dict[str, StrategyResult]) -> dict:
    baselines = {n: r for n, r in results.items() if n not in MODEL_NAMES}
    best_base_name, best_base = max(
        ((n, r.metrics.get("mean_weekly_net", float("-inf"))) for n, r in baselines.items()),
        key=lambda x: x[1],
        default=(None, float("-inf")),
    )
    out: dict = {"best_baseline": best_base_name, "models": {}}
    def _num(m: dict, key: str, missing: float) -> float:
        value = m.get(key)
        return missing if value is None else float(value)

    for name in MODEL_NAMES & results.keys():
        m = results[name].metrics
        mean_net = _num(m, "mean_weekly_net", float("-inf"))
        checks = {
            "positive_after_costs": mean_net > 0,
            "beats_best_baseline": mean_net > best_base,
            "ic_significant": _num(m, "ic_tstat", 0.0) >= MIN_IC_TSTAT,
            "consistent": _num(m, "consistency_13w", 0.0) >= MIN_CONSISTENCY,
        }
        passed = all(checks.values())
        failed = [k for k, ok in checks.items() if not ok]
        out["models"][name] = {
            "passed": passed,
            "checks": checks,
            "summary_tr": (
                "Model, maliyet sonrası kıyasları tutarlı biçimde yendi. Holdout ile teyit edilmeden canlı kullanılmamalı."
                if passed
                else "Tutarlı bir avantaj bulunamadı. Başarısız kriterler: " + ", ".join(failed) + "."
            ),
        }
    return out


def predict_next_week(panel: Panel, strategy, top_n: int) -> dict:
    """Train on everything known, then rank the latest week's stocks for next week."""
    latest = int(panel.week.max())
    train = np.isfinite(panel.y_rank)
    if hasattr(strategy, "reset"):
        strategy.reset()  # always retrain on every known week before forecasting
    if strategy.trains:
        strategy.fit(panel.X[train], panel.y_rank[train])
    rows = panel.week == latest
    scores = strategy.predict(panel.X[rows])
    syms = panel.symbols[rows]
    order = np.argsort(-scores, kind="stable")
    return {
        "as_of_week_end": panel.week_end[latest],
        "model": strategy.name,
        "picks": [{"symbol": str(syms[i]), "score": round(float(scores[i]), 5)} for i in order[:top_n]],
        "ranked": [{"symbol": str(syms[i]), "score": round(float(scores[i]), 5)} for i in order],
    }
