"""Deterministic scoring configuration.

The flow score is a weighted sum of normalised components that sum to 100.
These weights are intentionally explicit and version-stamped so that a signal
can be reconstructed exactly (spec requirement: "the original data used to
generate a signal must be reconstructable").
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

SCORING_VERSION = "1.0.0"

# Component weights — must sum to 100.
DEFAULT_WEIGHTS: dict[str, float] = {
    "price_momentum": 15.0,
    "volume": 20.0,
    "volume_acceleration": 10.0,
    "price_structure": 15.0,
    "volatility": 10.0,
    "technical": 15.0,
    "news": 15.0,
}


@dataclass(frozen=True)
class ScoringConfig:
    version: str = SCORING_VERSION
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))

    def __post_init__(self) -> None:
        total = sum(self.weights.values())
        # Allow a small tolerance for float/rounding noise from calibration.
        if abs(total - 100.0) > 0.5:
            raise ValueError(f"Scoring weights must sum to ~100, got {total}")


def load_weights(raw: str | None) -> dict[str, float]:
    """Parse a ``SCORING_WEIGHTS`` JSON override, renormalised to sum to 100.

    Missing components fall back to their default weight; unknown keys are
    ignored. A missing/empty/invalid override yields the default weights.
    """
    if not raw or not raw.strip():
        return dict(DEFAULT_WEIGHTS)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return dict(DEFAULT_WEIGHTS)
    weights = {k: float(data.get(k, DEFAULT_WEIGHTS[k])) for k in DEFAULT_WEIGHTS}
    total = sum(weights.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: v / total * 100 for k, v in weights.items()}


def scoring_config_from_settings(settings=None) -> ScoringConfig:
    """Build a ScoringConfig from the (optional) SCORING_WEIGHTS setting."""
    from .config import get_settings

    settings = settings or get_settings()
    return ScoringConfig(weights=load_weights(settings.scoring_weights))


# Direction thresholds. Lower bound inclusive, upper bound exclusive, except the
# top band which is inclusive of 100.
DIRECTION_THRESHOLDS: list[tuple[float, float, str]] = [
    (0.0, 25.0, "STRONG_NEGATIVE"),
    (25.0, 40.0, "NEGATIVE"),
    (40.0, 60.0, "NEUTRAL"),
    (60.0, 75.0, "POSITIVE"),
    (75.0, 90.0, "STRONG_POSITIVE"),
    (90.0, 100.01, "EXTREME_POSITIVE"),
]
