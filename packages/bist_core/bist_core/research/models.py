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


class BoostedRanker:
    """Gradient-boosted trees (scikit-learn) on the same features and target as
    the ridge model. Unlike ridge it can learn non-linear rules and
    interactions ("momentum helps, but only when volatility is low").

    Retrained from scratch on all earlier weeks every ``refit_every`` calls;
    between refits the last model is reused, which never looks ahead because
    it was trained on even older weeks. Shallow trees, strong leaf limits and
    early stopping keep it from memorising noise.
    """

    name = "boosting"
    trains = True

    def __init__(self, refit_every: int = 4, seed: int = 0):
        self.refit_every = refit_every
        self.seed = seed
        self._model = None
        self._calls = 0

    def reset(self) -> None:
        """Forget the model so the next fit always retrains (used before a final forecast)."""
        self._model, self._calls = None, 0

    def fit(self, X: np.ndarray, y: np.ndarray) -> BoostedRanker:
        due = self._model is None or self._calls % self.refit_every == 0
        self._calls += 1
        if not due or len(y) < 200:
            return self
        from sklearn.ensemble import HistGradientBoostingRegressor

        self._model = HistGradientBoostingRegressor(
            max_depth=3, learning_rate=0.05, max_iter=150, min_samples_leaf=100,
            l2_regularization=1.0, early_stopping=True, validation_fraction=0.2,
            n_iter_no_change=15, random_state=self.seed,
        ).fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self._model is None:
            return np.zeros(len(X))  # not enough history yet: no opinion
        return self._model.predict(X)


def boosting_available() -> bool:
    try:
        import sklearn  # noqa: F401
    except ImportError:
        return False
    return True


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


MODEL_NAMES = {"ridge", "boosting"}


def default_strategies(lam: float = 10.0, seed: int = 7, *, with_fx: bool = False) -> list:
    """``with_fx`` adds the USD/TRY rule; only meaningful when FX data was given."""
    fx = [FeatureBaseline("fx_tilt", "fx_beta_x_trend", +1.0)] if with_fx else []
    boosted = [BoostedRanker(seed=seed)] if boosting_available() else []
    return [
        *fx,
        RidgeRanker(lam=lam),
        *boosted,
        FeatureBaseline("momentum_12w", "ex_ret_12w", +1.0),
        FeatureBaseline("momentum_4w", "ex_ret_4w", +1.0),
        FeatureBaseline("reversal_1w", "ex_ret_1w", -1.0),
        FeatureBaseline("low_vol_12w", "vol_12w", -1.0),
        FeatureBaseline("near_high_12w", "dist_from_12w_high", +1.0),
        RandomBaseline(seed=seed),
    ]
