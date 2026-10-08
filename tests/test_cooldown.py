from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bist_core.enums import SignalChange
from bist_core.notifications import AlertCooldown

T0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)


def test_first_alert_always_sent():
    cd = AlertCooldown(cooldown_seconds=600, min_score_delta=10)
    assert cd.should_send("KTLEV", score=80, change=SignalChange.STRENGTHENING, now=T0) is True


def test_throttled_within_cooldown():
    cd = AlertCooldown(cooldown_seconds=600, min_score_delta=10)
    cd.should_send("KTLEV", score=80, change=SignalChange.STRENGTHENING, now=T0)
    # 5 minutes later, still inside the 10-min cooldown.
    assert cd.should_send("KTLEV", score=92, change=SignalChange.STRENGTHENING, now=T0 + timedelta(minutes=5)) is False


def test_sent_after_cooldown_with_sufficient_delta():
    cd = AlertCooldown(cooldown_seconds=600, min_score_delta=10)
    cd.should_send("KTLEV", score=80, change=SignalChange.STRENGTHENING, now=T0)
    assert cd.should_send("KTLEV", score=65, change=SignalChange.WEAKENING, now=T0 + timedelta(minutes=11)) is True


def test_suppressed_after_cooldown_when_delta_too_small():
    cd = AlertCooldown(cooldown_seconds=600, min_score_delta=10)
    cd.should_send("KTLEV", score=80, change=SignalChange.STRENGTHENING, now=T0)
    assert cd.should_send("KTLEV", score=83, change=SignalChange.STRENGTHENING, now=T0 + timedelta(minutes=11)) is False


def test_reversal_bypasses_cooldown():
    cd = AlertCooldown(cooldown_seconds=600, reversal_cooldown_seconds=0, min_score_delta=10)
    cd.should_send("KTLEV", score=86, change=SignalChange.STRENGTHENING, now=T0)
    # Reversal 1 minute later is sent immediately despite the cooldown.
    assert cd.should_send("KTLEV", score=42, change=SignalChange.REVERSAL, now=T0 + timedelta(minutes=1)) is True
