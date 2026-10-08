"""Signal assembly pipeline.

Pure compute: given the raw inputs (recent ticks, current quote, daily history,
news) it produces the flow/volume/technical metrics, the deterministic score,
anomalies and a ready-to-persist :class:`SignalPayload`. No I/O here, so it is
reused by both the signal-engine worker and the API, and is easy to test.
"""
from __future__ import annotations

from datetime import UTC, datetime
from itertools import pairwise

from .engines.anomaly import AnomalyEngine
from .engines.flow import FlowEngine
from .engines.indicators import atr, ema, rsi, sma, vwap
from .engines.scoring import ScoringEngine
from .engines.signal_change import classify_change
from .engines.volume import VolumeEngine, baseline_from_history
from .enums import DataStatus
from .schemas import (
    Anomaly,
    NewsEvent,
    OhlcvBar,
    Quote,
    ScoreResult,
    SignalPayload,
    TechnicalMetrics,
    Tick,
)


def _news_score(news: list[NewsEvent]) -> float:
    if not news:
        return 0.5
    # Importance-weighted lift; capped so news never dominates.
    lift = min(sum(n.importance for n in news) / 20.0, 0.4)
    return 0.5 + lift


def _technicals(ticks: list[Tick], history: list[OhlcvBar]) -> TechnicalMetrics:
    prices = [t.price for t in ticks]
    closes = [b.close for b in history] + prices
    highs = [b.high for b in history]
    lows = [b.low for b in history]
    # Per-interval volume deltas for VWAP.
    vwap_prices, vwap_vols = [], []
    for prev, cur in pairwise(ticks):
        dv = cur.volume - prev.volume
        vwap_prices.append(cur.price)
        vwap_vols.append(dv if dv >= 0 else cur.volume)
    return TechnicalMetrics(
        ema_9=ema(prices, 9),
        sma_20=sma(prices, 20) or sma(closes, 20),
        rsi_14=rsi(prices, 14) or rsi(closes, 14),
        atr_14=atr(highs, lows, [b.close for b in history], 14),
        vwap=vwap(vwap_prices, vwap_vols),
    )


class SignalPipeline:
    def __init__(self):
        self.flow_engine = FlowEngine()
        self.volume_engine = VolumeEngine()
        self.scoring = ScoringEngine()
        self.anomaly_engine = AnomalyEngine()

    def assemble(
        self,
        *,
        quote: Quote,
        ticks: list[Tick],
        history: list[OhlcvBar] | None = None,
        news: list[NewsEvent] | None = None,
        previous_score: float | None = None,
    ) -> tuple[ScoreResult, list[Anomaly], SignalPayload]:
        history = history or []
        news = news or []

        flow = self.flow_engine.compute(ticks)
        baseline = baseline_from_history([b.volume for b in history])
        volume = self.volume_engine.compute(ticks, baseline_per_minute=baseline)
        technical = _technicals(ticks, history)

        score = self.scoring.score(
            price=quote.price,
            flow=flow,
            volume=volume,
            technical=technical,
            change_percent=quote.change_percent,
            high=quote.high,
            low=quote.low,
            news_score=_news_score(news),
            data_status=quote.data_status,
            n_ticks=len(ticks),
        )

        anomalies = self.anomaly_engine.detect(
            symbol=quote.symbol,
            flow=flow,
            volume=volume,
            price=quote.price,
            intraday_high=quote.high,
            intraday_low=quote.low,
            timestamp=quote.timestamp,
        )

        change = classify_change(previous_score, score.score)

        evidence = [f"{c.name}={c.raw:.2f}" for c in score.components if abs(c.raw - 0.5) > 0.1]
        evidence += [a.evidence for a in anomalies[:3]]
        risks = []
        if quote.data_status in (DataStatus.DELAYED, DataStatus.STALE):
            risks.append(f"{quote.data_status.value.lower()} market data")
        risks.append("no confirmed institutional (AKD) context")
        invalidation = (
            ["flow score below 60", "momentum reversal"]
            if score.score >= 60
            else ["flow score above 40", "momentum turns positive"]
        )

        payload = SignalPayload(
            symbol=quote.symbol,
            timestamp=quote.timestamp or datetime.now(UTC),
            score=score.score,
            direction=score.direction,
            confidence=score.confidence,
            change=change,
            evidence=evidence or ["neutral evidence across components"],
            risks=risks,
            invalidation_conditions=invalidation,
            data_status=quote.data_status,
            data_snapshot=score.data_snapshot | {"anomalies": [a.model_dump(mode="json") for a in anomalies]},
        )
        return score, anomalies, payload
