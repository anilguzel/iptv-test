from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bist_core.engines.backtest import BacktestEngine, BacktestSignal, PricePoint

T0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)


def _price_series(values: list[float]) -> list[PricePoint]:
    return [PricePoint(timestamp=T0 + timedelta(minutes=i), price=v) for i, v in enumerate(values)]


def test_entry_uses_price_at_signal_not_future():
    # Prices: flat at 10 up to minute 10, then jump to 11 at minute 11+.
    values = [10.0] * 11 + [11.0] * 60
    prices = _price_series(values)
    sig = BacktestSignal(timestamp=T0 + timedelta(minutes=10), symbol="X", direction="POSITIVE", score=80)

    outcome = BacktestEngine(primary_horizon=30).evaluate_signal(sig, prices)
    assert outcome is not None
    assert outcome.entry_price == 10.0  # price known AT signal time, not the future 11.0
    # Long return at +30m: (11 - 10) / 10 = +0.10
    assert outcome.returns[30] == 0.10


def test_no_lookahead_beyond_horizon():
    # A huge spike at minute 90 must NOT affect the 30m return.
    values = [10.0] * 11 + [10.5] * 40 + [100.0] * 60
    prices = _price_series(values)
    sig = BacktestSignal(timestamp=T0 + timedelta(minutes=10), symbol="X", direction="POSITIVE", score=80)

    outcome = BacktestEngine(primary_horizon=30).evaluate_signal(sig, prices)
    assert outcome.returns[30] == 0.05  # (10.5 - 10) / 10, spike ignored


def test_short_direction_inverts_return():
    values = [10.0] * 11 + [9.0] * 60
    prices = _price_series(values)
    sig = BacktestSignal(timestamp=T0 + timedelta(minutes=10), symbol="X", direction="NEGATIVE", score=20)
    outcome = BacktestEngine(primary_horizon=30).evaluate_signal(sig, prices)
    # Price fell 10% -> a short "wins" -> positive signed return.
    assert outcome.returns[30] == 0.10


def test_neutral_signal_not_traded():
    prices = _price_series([10.0] * 40)
    sig = BacktestSignal(timestamp=T0 + timedelta(minutes=5), symbol="X", direction="NEUTRAL", score=50)
    assert BacktestEngine().evaluate_signal(sig, prices) is None


def test_aggregate_report():
    values = [10.0] * 11 + [11.0] * 60
    prices = {"X": _price_series(values)}
    signals = [
        BacktestSignal(timestamp=T0 + timedelta(minutes=10), symbol="X", direction="POSITIVE", score=80),
        # Also before the jump, so both capture the move.
        BacktestSignal(timestamp=T0 + timedelta(minutes=5), symbol="X", direction="POSITIVE", score=78),
    ]
    report = BacktestEngine(primary_horizon=30).run(signals, prices)
    assert report.signal_count == 2
    assert report.win_rate == 1.0
    assert report.average_return > 0
