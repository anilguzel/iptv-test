from __future__ import annotations

from bist_core.engines.signal_change import classify_change, is_material
from bist_core.enums import SignalChange


def test_reversal_strong_positive_to_neutral():
    # Spec example: 86 STRONG_POSITIVE -> 42 NEUTRAL => SIGNAL_REVERSAL
    assert classify_change(86, 42) == SignalChange.REVERSAL


def test_strengthening():
    assert classify_change(62, 78) == SignalChange.STRENGTHENING


def test_weakening_on_band_drop():
    # 78 STRONG_POSITIVE -> 69 POSITIVE: band dropped -> weakening.
    assert classify_change(78, 69) == SignalChange.WEAKENING


def test_stable_small_move_same_band():
    assert classify_change(62, 64) == SignalChange.STABLE


def test_first_signal_is_stable():
    assert classify_change(None, 80) == SignalChange.STABLE


def test_is_material():
    assert is_material(None, 50) is True
    assert is_material(50, 61) is True  # crosses NEUTRAL->POSITIVE band
    assert is_material(50, 52) is False
