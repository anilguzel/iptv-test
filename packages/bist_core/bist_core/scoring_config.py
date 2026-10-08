"""Deterministic scoring configuration.

The flow score is a weighted sum of normalised components that sum to 100.
These weights are intentionally explicit and version-stamped so that a signal
can be reconstructed exactly (spec requirement: "the original data used to
generate a signal must be reconstructable").
"""
from __future__ import annotations

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
        total = round(sum(self.weights.values()), 6)
        if total != 100.0:
            raise ValueError(f"Scoring weights must sum to 100, got {total}")


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
