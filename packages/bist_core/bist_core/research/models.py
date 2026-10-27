"""Ranking models and the baselines a model must beat.

A strategy scores each stock for next week; higher = expected to beat the
benchmark by more. Baselines need no training. A model that cannot beat them
out of sample has learned nothing useful.
"""
from __future__ import annotations

import numpy as np

from .features import FEATURE_NAMES


class RidgeRanker:
    """Linear model on z-scored features, fit to the cross-sectional rank target.

    Closed-form ridge regression; simple, fast and explainable (one coefficient
    per feature). The intercept is not penalised.
    """

    name = "ridge"
    trains = True

    def __init__(self, lam: float = 10.0):
        self.lam = lam
        self.coef_: np.ndarray | None = None
        self.intercept_: float = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray) -> RidgeRanker:
        n, k = X.shape
        A = np.hstack([np.ones((n, 1)), X])
        penalty = self.lam * np.eye(k + 1)
        penalty[0, 0] = 0.0
        w = np.linalg.solve(A.T @ A + penalty, A.T @ y)
        self.intercept_, self.coef_ = float(w[0]), w[1:]
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.coef_ is None:
            raise RuntimeError("RidgeRanker.predict called before fit")
        return self.intercept_ + X @ self.coef_

    def coefficients(self) -> dict[str, float]:
        if self.coef_ is None:
            return {}
        return {name: round(float(c), 5) for name, c in zip(FEATURE_NAMES, self.coef_, strict=True)}


class FeatureBaseline:
    """Rank by one feature (no training): e.g. momentum or short-term reversal."""

    trains = False

    def __init__(self, name: str, feature: str, sign: float = 1.0):
        self.name = name
        self._idx = FEATURE_NAMES.index(feature)
        self._sign = sign

    def fit(self, X: np.ndarray, y: np.ndarray) -> FeatureBaseline:
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self._sign * X[:, self._idx]


class RandomBaseline:
    """Random ranking: what pure luck looks like."""

    name = "random"
    trains = False

    def __init__(self, seed: int = 7):
        self._rng = np.random.default_rng(seed)

    def fit(self, X: np.ndarray, y: np.ndarray) -> RandomBaseline:
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self._rng.standard_normal(len(X))


MODEL_NAMES = {"ridge"}


def default_strategies(lam: float = 10.0, seed: int = 7) -> list:
    return [
        RidgeRanker(lam=lam),
        FeatureBaseline("momentum_12w", "ex_ret_12w", +1.0),
        FeatureBaseline("momentum_4w", "ex_ret_4w", +1.0),
        FeatureBaseline("reversal_1w", "ex_ret_1w", -1.0),
        FeatureBaseline("low_vol_12w", "vol_12w", -1.0),
        FeatureBaseline("near_high_12w", "dist_from_12w_high", +1.0),
        RandomBaseline(seed=seed),
    ]
