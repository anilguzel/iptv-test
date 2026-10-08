from __future__ import annotations

from bist_core.engines.flow import FlowEngine
from conftest import make_ticks


def test_rising_price_and_volume_gives_positive_flow():
    # 41 ticks, 1 min apart, steadily rising price with steady volume growth.
    prices = [10.0 + 0.05 * i for i in range(41)]
    volumes = [1000.0 * i for i in range(41)]
    ticks = make_ticks(prices, volumes)

    m = FlowEngine().compute(ticks)
    assert m.flow_5m > 0
    assert m.flow_15m > 0
    assert m.flow_day > 0
    assert m.price_momentum > 0


def test_flow_acceleration_positive_when_recent_window_stronger():
    # First 25 min: mild up. Last 15 min: much stronger volume & price advance.
    prices = [10.0 + 0.01 * i for i in range(26)] + [10.26 + 0.1 * i for i in range(1, 16)]
    volumes = [500.0 * i for i in range(26)] + [13000.0 + 5000.0 * i for i in range(1, 16)]
    ticks = make_ticks(prices, volumes)

    m = FlowEngine().compute(ticks)
    assert m.flow_acceleration > 0, "recent 15m flow should exceed the prior 15m"


def test_falling_price_gives_negative_flow():
    prices = [20.0 - 0.05 * i for i in range(41)]
    volumes = [1000.0 * i for i in range(41)]
    ticks = make_ticks(prices, volumes)

    m = FlowEngine().compute(ticks)
    assert m.flow_5m < 0
    assert m.price_momentum < 0


def test_insufficient_ticks_returns_zero_metrics():
    m = FlowEngine().compute(make_ticks([10.0], [1000.0]))
    assert m.flow_5m == 0.0 and m.flow_day == 0.0
