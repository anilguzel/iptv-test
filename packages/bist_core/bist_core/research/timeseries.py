"""Single-stock walk-forward: predict one stock's next week from its own past.

There is nothing to rank against, so each strategy turns its score into a
position: LONG when the score is positive, otherwise FLAT (cash, zero excess).
Shorting a thin small-cap is rarely practical, so it is not modelled.

Leakage control: feature standardisation statistics come from the training
weeks only, and training never includes a week whose outcome is unknown at the
signal week's close (feature week < t).

Statistical reality check: ~150 weekly observations is very little. Expect
most single-stock models to fail the verdict; that is an honest result.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .features import FEATURE_NAMES, Panel
from .models import RidgeRanker
from .walkforward import StrategyResult, WalkForwardConfig, return_stats, spearman

CLIP_SIGMA = 3.0  # winsorise targets/features at +-3 training std (micro-cap spikes)


class TSRidge:
    """Ridge on features standardised with TRAINING-ONLY mean/std; target clipped."""

    name = "ridge"
    trains = True

    def __init__(self, lam: float = 10.0):
        self._ridge = RidgeRanker(lam=lam)
        self._mu: np.ndarray | None = None
        self._sd: np.ndarray | None = None

    def _z(self, X: np.ndarray) -> np.ndarray:
        return np.clip((X - self._mu) / self._sd, -CLIP_SIGMA, CLIP_SIGMA)

    def fit(self, X: np.ndarray, y: np.ndarray) -> TSRidge:
        self._mu = X.mean(axis=0)
        sd = X.std(axis=0)
        self._sd = np.where(sd < 1e-12, 1.0, sd)
        y_mu, y_sd = y.mean(), y.std() or 1.0
        y_clipped = np.clip(y, y_mu - CLIP_SIGMA * y_sd, y_mu + CLIP_SIGMA * y_sd)
        self._ridge.fit(self._z(X), y_clipped)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self._mu is None:
            raise RuntimeError("TSRidge.predict called before fit")
        return self._ridge.predict(self._z(X))

    def coefficients(self) -> dict[str, float]:
        return self._ridge.coefficients()


class ConstantLong:
    """Always hold the stock (buy-and-hold, in excess of the benchmark)."""

    name = "always_long"
    trains = False

    def fit(self, X, y):
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.ones(len(X))


class RawFeatureSign:
    """Long when a raw feature is positive, e.g. 4-week excess momentum."""

    trains = False

    def __init__(self, name: str, feature: str):
        self.name = name
        self._idx = FEATURE_NAMES.index(feature)

    def fit(self, X, y):
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return X[:, self._idx]


class CoinFlip:
    name = "random"
    trains = False

    def __init__(self, seed: int = 7):
        self._rng = np.random.default_rng(seed)

    def fit(self, X, y):
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self._rng.standard_normal(len(X))


def default_ts_strategies(lam: float = 10.0, seed: int = 7) -> list:
    return [TSRidge(lam=lam), ConstantLong(), RawFeatureSign("momentum_4w", "ex_ret_4w"), CoinFlip(seed=seed)]


@dataclass
class TSStep:
    week: int
    signal_week_end: str
    hold_week_end: str
    train_max_week: int
    n_train: int
    score: float
    position: float
    outcome: float  # next week's excess return of the stock
    net: float
    turnover: float


def effective_n(x: np.ndarray, y: np.ndarray, max_lag: int | None = None) -> float:
    """Bartlett's effective sample size for the correlation of two series.

    1/n_eff = (1/n) * (1 + 2 * sum_k rho_x(k) * rho_y(k)). Shrinks n only when
    BOTH series are autocorrelated (white-noise outcomes leave it ~unchanged),
    which is when a naive correlation t-test would overstate significance.
    """
    n = len(x)
    if n < 4:
        return float(n)
    max_lag = max_lag or max(1, min(10, n // 4))

    def acf(a: np.ndarray, k: int) -> float:
        a = a - a.mean()
        denom = float((a * a).sum())
        return float((a[:-k] * a[k:]).sum() / denom) if denom > 0 else 0.0

    inflation = 1 + 2 * sum(acf(x, k) * acf(y, k) for k in range(1, max_lag + 1))
    return float(min(n, max(3.0, n / max(inflation, 1e-9))))


def binomial_pvalue_greater(k: int, n: int, p: float = 0.5) -> float:
    """One-sided P(X >= k) for X ~ Binomial(n, p): is accuracy better than a coin?"""
    if n == 0:
        return 1.0
    return float(sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1)))


def run_ts_strategy(panel: Panel, strategy, weeks: list[int], cfg: WalkForwardConfig) -> StrategyResult:
    """Walk forward over a single-stock panel (one row per week)."""
    if len(set(panel.symbols.tolist())) != 1:
        raise ValueError("time-series mode expects a panel with exactly one symbol")
    has_target = np.isfinite(panel.y_raw)
    cost = cfg.cost_bps_per_side / 1e4  # each entry or exit is one trade
    steps: list[TSStep] = []
    prev_pos = 0.0
    for t in weeks:
        train = (panel.week < t) & has_target
        if strategy.trains:
            strategy.fit(panel.X_raw[train], panel.y_raw[train])
        row = np.flatnonzero((panel.week == t) & has_target)
        if len(row) != 1:
            continue
        i = int(row[0])
        score = float(strategy.predict(panel.X_raw[i:i + 1])[0])
        position = 1.0 if score > 0 else 0.0
        outcome = float(panel.y_raw[i])
        turnover = abs(position - prev_pos)
        prev_pos = position
        hold_idx = t + 1 if t + 1 < len(panel.week_end) else t
        steps.append(
            TSStep(
                week=int(t),
                signal_week_end=panel.week_end[t],
                hold_week_end=panel.week_end[hold_idx],
                train_max_week=int(panel.week[train].max()) if train.any() else -1,
                n_train=int(train.sum()),
                score=score,
                position=position,
                outcome=outcome,
                net=position * outcome - turnover * cost,
                turnover=turnover,
            )
        )
    result = StrategyResult(name=strategy.name)
    result.steps = steps  # type: ignore[assignment]  # TSStep, not cross-sectional Step
    result.metrics = ts_metrics(steps)
    return result


def ts_metrics(steps: list[TSStep]) -> dict:
    if not steps:
        return {"weeks": 0}
    net = np.array([s.net for s in steps])
    scores = np.array([s.score for s in steps])
    outcomes = np.array([s.outcome for s in steps])
    positions = np.array([s.position for s in steps])

    correct = ((positions == 1) & (outcomes > 0)) | ((positions == 0) & (outcomes <= 0))
    k, n = int(correct.sum()), len(correct)
    ic = spearman(scores, outcomes)
    # t-stat on the Bartlett effective sample size (autocorrelation-robust).
    n_eff = effective_n(scores.argsort().argsort().astype(float), outcomes.argsort().argsort().astype(float))
    ic_t = None
    if ic is not None and n_eff > 2 and abs(ic) < 1:
        ic_t = round(ic * math.sqrt((n_eff - 2) / (1 - ic**2)), 3)
    return {
        **return_stats(net, [s.hold_week_end for s in steps]),
        "hit_rate": round(k / n, 4),  # directional accuracy (long when up, flat when not)
        "accuracy_pvalue": round(binomial_pvalue_greater(k, n), 4),
        "mean_ic": None if ic is None else round(ic, 4),
        "ic_tstat": ic_t,
        "ic_effective_n": round(n_eff, 1),
        "exposure": round(float(positions.mean()), 4),
        "mean_turnover": round(float(np.mean([s.turnover for s in steps])), 4),
    }


def predict_next_week_ts(panel: Panel, strategy) -> dict:
    latest = int(panel.week.max())
    train = np.isfinite(panel.y_raw)
    if strategy.trains:
        strategy.fit(panel.X_raw[train], panel.y_raw[train])
    i = int(np.flatnonzero(panel.week == latest)[0])
    score = float(strategy.predict(panel.X_raw[i:i + 1])[0])
    return {
        "as_of_week_end": panel.week_end[latest],
        "model": strategy.name,
        "symbol": str(panel.symbols[i]),
        "predicted_excess": round(score, 6),
        "position": "LONG" if score > 0 else "FLAT",
    }
