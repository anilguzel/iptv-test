from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from bist_core.enums import DataStatus
from bist_core.providers.freshness import classify_freshness
from bist_core.schemas import Quote
from bist_core.validation import ValidationError, validate_quote

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def test_delayed_provider_is_never_live():
    status = classify_freshness(NOW - timedelta(seconds=30), provider_realtime=False, stale_after_seconds=180, now=NOW)
    assert status == DataStatus.DELAYED


def test_old_quote_is_stale():
    status = classify_freshness(NOW - timedelta(seconds=600), provider_realtime=False, stale_after_seconds=180, now=NOW)
    assert status == DataStatus.STALE


def test_realtime_provider_fresh_is_live():
    status = classify_freshness(NOW - timedelta(seconds=5), provider_realtime=True, stale_after_seconds=180, now=NOW)
    assert status == DataStatus.LIVE


def _q(**kw):
    base = dict(symbol="KTLEV", price=7.0, volume=1000.0, timestamp=NOW)
    base.update(kw)
    return Quote(**base)


def test_validate_rejects_nonpositive_price():
    with pytest.raises(ValidationError):
        validate_quote(_q(price=0.0))


def test_validate_rejects_negative_volume():
    with pytest.raises(ValidationError):
        validate_quote(_q(volume=-5.0))


def test_validate_rejects_future_timestamp():
    with pytest.raises(ValidationError):
        validate_quote(_q(timestamp=datetime.now(UTC) + timedelta(hours=1)))


def test_validate_rejects_unknown_symbol():
    with pytest.raises(ValidationError):
        validate_quote(_q(symbol="ZZZZ"), known_symbols={"KTLEV", "THYAO"})


def test_validate_accepts_good_quote():
    q = validate_quote(_q(timestamp=datetime.now(UTC)), known_symbols={"KTLEV"})
    assert q.symbol == "KTLEV"
