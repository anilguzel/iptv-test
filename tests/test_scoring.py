from __future__ import annotations

from bist_core.engines.scoring import ScoringEngine, score_to_direction
from bist_core.enums import DataStatus, SignalDirection
from bist_core.schemas import FlowMetrics, TechnicalMetrics, VolumeMetrics


def test_all_neutral_inputs_score_exactly_50():
    engine = ScoringEngine()
    res = engine.score(
        price=10.0,
        flow=FlowMetrics(),
        volume=VolumeMetrics(),
        technical=TechnicalMetrics(),
        change_percent=None,
        high=None,
        low=None,
        news_score=0.5,
        data_status=DataStatus.DELAYED,
        n_ticks=50,
    )
    assert res.score == 50.0
    assert res.direction == SignalDirection.NEUTRAL
    # Components must be fully reconstructable.
    assert len(res.components) == 7
    assert res.data_snapshot["component_norms"]["volume"] == 0.5


def test_bullish_inputs_score_high():
    engine = ScoringEngine()
    flow = FlowMetrics(price_momentum=0.04, flow_5m=5e6, flow_15m=1e7, flow_acceleration=8e6)
    vol = VolumeMetrics(volume_ratio_5m=5.0)
    tech = TechnicalMetrics(ema_9=10.5, sma_20=10.0, rsi_14=72.0, atr_14=0.3)
    res = engine.score(
        price=11.0, flow=flow, volume=vol, technical=tech,
        change_percent=4.0, high=11.0, low=10.0, news_score=0.7,
        data_status=DataStatus.DELAYED, n_ticks=60,
    )
    assert res.score >= 75.0
    assert res.direction in (SignalDirection.STRONG_POSITIVE, SignalDirection.EXTREME_POSITIVE)


def test_bearish_inputs_score_low():
    engine = ScoringEngine()
    flow = FlowMetrics(price_momentum=-0.04, flow_5m=-5e6, flow_15m=-1e7, flow_acceleration=-8e6)
    vol = VolumeMetrics(volume_ratio_5m=5.0)
    tech = TechnicalMetrics(ema_9=9.5, sma_20=10.0, rsi_14=28.0, atr_14=0.3)
    res = engine.score(
        price=9.0, flow=flow, volume=vol, technical=tech,
        change_percent=-4.0, high=10.0, low=9.0, news_score=0.3,
        data_status=DataStatus.DELAYED, n_ticks=60,
    )
    assert res.score <= 30.0
    assert res.direction in (SignalDirection.NEGATIVE, SignalDirection.STRONG_NEGATIVE)


def test_stale_data_downgrades_confidence():
    engine = ScoringEngine()
    base = dict(price=10.0, flow=FlowMetrics(), volume=VolumeMetrics(), technical=TechnicalMetrics(), n_ticks=60)
    delayed = engine.score(**base, data_status=DataStatus.DELAYED)
    stale = engine.score(**base, data_status=DataStatus.STALE)
    assert stale.confidence < delayed.confidence


def test_direction_thresholds():
    assert score_to_direction(10) == SignalDirection.STRONG_NEGATIVE
    assert score_to_direction(50) == SignalDirection.NEUTRAL
    assert score_to_direction(83) == SignalDirection.STRONG_POSITIVE
    assert score_to_direction(95) == SignalDirection.EXTREME_POSITIVE
    assert score_to_direction(100) == SignalDirection.EXTREME_POSITIVE
