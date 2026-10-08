"""Signal-change detector: strengthening / weakening / reversal."""
from __future__ import annotations

from ..enums import SignalChange
from .scoring import score_to_direction

_RANK = {
    "STRONG_NEGATIVE": 0,
    "NEGATIVE": 1,
    "NEUTRAL": 2,
    "POSITIVE": 3,
    "STRONG_POSITIVE": 4,
    "EXTREME_POSITIVE": 5,
}


def classify_change(
    previous_score: float | None,
    current_score: float,
    *,
    min_delta: float = 10.0,
    reversal_delta: float = 25.0,
) -> SignalChange:
    """Classify the transition between two consecutive flow scores.

    A reversal is a large move (>= ``reversal_delta``) that leaves a directional
    stance (e.g. 86 STRONG_POSITIVE -> 42 NEUTRAL).
    """
    if previous_score is None:
        return SignalChange.STABLE

    delta = current_score - previous_score
    prev_pos, cur_pos = previous_score >= 60, current_score >= 60
    prev_neg, cur_neg = previous_score <= 40, current_score <= 40

    leaving_bull = prev_pos and not cur_pos
    leaving_bear = prev_neg and not cur_neg
    flipped = (prev_pos and cur_neg) or (prev_neg and cur_pos)
    if abs(delta) >= reversal_delta and (leaving_bull or leaving_bear or flipped):
        return SignalChange.REVERSAL

    prev_rank = _RANK[score_to_direction(previous_score).value]
    cur_rank = _RANK[score_to_direction(current_score).value]
    if cur_rank > prev_rank or delta >= min_delta:
        return SignalChange.STRENGTHENING
    if cur_rank < prev_rank or delta <= -min_delta:
        return SignalChange.WEAKENING
    return SignalChange.STABLE


def is_material(previous_score: float | None, current_score: float, *, min_delta: float = 10.0) -> bool:
    """Whether the change warrants recording a new signal-history state."""
    if previous_score is None:
        return True
    if abs(current_score - previous_score) >= min_delta:
        return True
    return score_to_direction(previous_score) != score_to_direction(current_score)
