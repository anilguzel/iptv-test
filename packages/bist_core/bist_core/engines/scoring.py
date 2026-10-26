"""Deterministic flow-score engine (0-100).

The score is a weighted sum of normalised components (each in 0..1, 0.5 =
neutral), so an all-neutral input yields exactly 50. The AI layer only
*explains* this score; it never computes it.

The score is the STRENGTH OF CURRENT EVIDENCE, not a probability of the price
rising. "83/100" does not mean "83% chance up".
"""
from __future__ import annotations

from ..enums import DataStatus, SignalDirection
from ..schemas import (
    FlowMetrics,
    ScoreComponent,
    ScoreResult,
    TechnicalMetrics,
    VolumeMetrics,
)
from ..scoring_config import DIRECTION_THRESHOLDS, ScoringConfig

_EPS = 1e-9


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def score_to_direction(score: float) -> SignalDirection:
    for lo, hi, name in DIRECTION_THRESHOLDS:
        if lo <= score < hi:
            return SignalDirection(name)
    return SignalDirection.NEUTRAL


class ScoringEngine:
    def __init__(self, config: ScoringConfig | None = None):
        self.config = config or ScoringConfig()

    # -- component normalisers (each returns 0..1) ------------------------- #
    def _price_momentum(self, flow: FlowMetrics) -> float:
        # 4% move over 5m saturates the component.
        return _clamp(0.5 + flow.price_momentum / 0.08, 0.0, 1.0)

    def _volume(self, flow: FlowMetrics, vol: VolumeMetrics) -> float:
        direction = flow.price_momentum if flow.price_momentum else flow.flow_5m
        sign = 1.0 if direction > 0 else (-1.0 if direction < 0 else 0.0)
        # ratio 5x saturates.
        magnitude = _clamp((vol.volume_ratio_5m - 1.0) / 8.0, 0.0, 0.5)
        return _clamp(0.5 + sign * magnitude, 0.0, 1.0)

    def _volume_acceleration(self, flow: FlowMetrics) -> float:
        denom = abs(flow.flow_15m) + abs(flow.flow_acceleration) + _EPS
        magnitude = abs(flow.flow_acceleration) / denom  # 0..1
        sign = 1.0 if flow.flow_acceleration > 0 else (-1.0 if flow.flow_acceleration < 0 else 0.0)
        return _clamp(0.5 + sign * 0.5 * magnitude, 0.0, 1.0)

    def _price_structure(
        self, price: float, tech: TechnicalMetrics, high: float | None, low: float | None, change_pct: float | None
    ) -> float:
        structure = 0.0
        has_signal = False
        if tech.ema_9 is not None:
            structure += 0.4 if price > tech.ema_9 else -0.4
            has_signal = True
        if tech.sma_20 is not None:
            structure += 0.3 if price > tech.sma_20 else -0.3
            has_signal = True
        if high is not None and low is not None and high > low:
            pos = (price - low) / (high - low)  # 0..1 position in day range
            structure += (pos - 0.5) * 0.6  # breakout bias
            has_signal = True
        if not has_signal:
            structure = _clamp((change_pct or 0.0) / 5.0, -1.0, 1.0) * 0.5
        return _clamp(0.5 + _clamp(structure, -1.0, 1.0) * 0.5, 0.0, 1.0)

    def _volatility(self, flow: FlowMetrics, tech: TechnicalMetrics) -> float:
        if tech.atr_14 is None:
            return 0.5
        sign = 1.0 if flow.price_momentum > 0 else (-1.0 if flow.price_momentum < 0 else 0.0)
        return _clamp(0.5 + sign * 0.15, 0.0, 1.0)

    def _technical(self, tech: TechnicalMetrics) -> float:
        if tech.rsi_14 is None:
            return 0.5
        base = 0.5 + (tech.rsi_14 - 50.0) / 100.0
        if tech.ema_9 is not None and tech.sma_20 is not None:
            base += 0.1 if tech.ema_9 > tech.sma_20 else -0.1
        return _clamp(base, 0.0, 1.0)

    # -- confidence -------------------------------------------------------- #
    def _confidence(self, data_status: DataStatus, n_ticks: int) -> float:
        conf = {
            DataStatus.LIVE: 1.0,
            DataStatus.DELAYED: 0.85,
            DataStatus.DEMO: 0.9,
            DataStatus.STALE: 0.4,
        }.get(data_status, 0.7)
        if n_ticks < 10:
            conf *= 0.6
        elif n_ticks < 30:
            conf *= 0.85
        return round(_clamp(conf, 0.05, 1.0), 4)

    # -- public API -------------------------------------------------------- #
    def score(
        self,
        *,
        price: float,
        flow: FlowMetrics,
        volume: VolumeMetrics,
        technical: TechnicalMetrics,
        change_percent: float | None = None,
        high: float | None = None,
        low: float | None = None,
        news_score: float = 0.5,
        data_status: DataStatus = DataStatus.DELAYED,
        n_ticks: int = 0,
    ) -> ScoreResult:
        norms = {
            "price_momentum": self._price_momentum(flow),
            "volume": self._volume(flow, volume),
            "volume_acceleration": self._volume_acceleration(flow),
            "price_structure": self._price_structure(price, technical, high, low, change_percent),
            "volatility": self._volatility(flow, technical),
            "technical": self._technical(technical),
            "news": _clamp(news_score, 0.0, 1.0),
        }
        components: list[ScoreComponent] = []
        total = 0.0
        for name, weight in self.config.weights.items():
            raw = norms[name]
            points = raw * weight
            total += points
            components.append(ScoreComponent(name=name, raw=round(raw, 4), weight=weight, points=round(points, 4)))

        score = round(_clamp(total, 0.0, 100.0), 2)
        confidence = self._confidence(data_status, n_ticks)

        return ScoreResult(
            score=score,
            direction=score_to_direction(score),
            confidence=confidence,
            components=components,
            scoring_version=self.config.version,
            data_snapshot={
                "price": price,
                "change_percent": change_percent,
                "flow": flow.model_dump(),
                "volume": volume.model_dump(),
                "technical": technical.model_dump(),
                "news_score": news_score,
                "data_status": data_status.value,
                "n_ticks": n_ticks,
                "component_norms": {k: round(v, 4) for k, v in norms.items()},
            },
        )
