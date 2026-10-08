"""Anomaly / unusual-activity detection with explicit, explainable thresholds."""
from __future__ import annotations

from datetime import UTC, datetime

from ..enums import AnomalySeverity, AnomalyType
from ..schemas import Anomaly, FlowMetrics, VolumeMetrics

# Thresholds (explicit so anomalies are explainable and reproducible).
VOLUME_SPIKE_RATIO = 3.0
VOLUME_SPIKE_CRITICAL_RATIO = 5.0
PRICE_MOVE_SPIKE = 0.03  # 3% over the 5m window
PRICE_MOVE_CRITICAL = 0.06
DIVERGENCE_FLOW_MISMATCH = True


class AnomalyEngine:
    def detect(
        self,
        *,
        symbol: str,
        flow: FlowMetrics,
        volume: VolumeMetrics,
        price: float,
        intraday_high: float | None = None,
        intraday_low: float | None = None,
        timestamp: datetime | None = None,
    ) -> list[Anomaly]:
        ts = timestamp or datetime.now(UTC)
        out: list[Anomaly] = []

        def add(t: AnomalyType, sev: AnomalySeverity, evidence: str, threshold=None, observed=None):
            out.append(
                Anomaly(
                    type=t, severity=sev, timestamp=ts, symbol=symbol,
                    evidence=evidence, threshold=threshold, observed=observed,
                )
            )

        # --- Volume ------------------------------------------------------- #
        r5 = volume.volume_ratio_5m
        if r5 >= VOLUME_SPIKE_CRITICAL_RATIO:
            add(AnomalyType.VOLUME_SPIKE, AnomalySeverity.CRITICAL, f"5m volume {r5:.1f}x baseline", VOLUME_SPIKE_CRITICAL_RATIO, r5)
        elif r5 >= VOLUME_SPIKE_RATIO:
            add(AnomalyType.VOLUME_SPIKE, AnomalySeverity.HIGH, f"5m volume {r5:.1f}x baseline", VOLUME_SPIKE_RATIO, r5)

        if flow.volume_acceleration > 0 and volume.volume_5m > 0 and flow.volume_acceleration > volume.volume_5m * 0.5:
            add(
                AnomalyType.VOLUME_ACCELERATION, AnomalySeverity.MEDIUM,
                "volume accelerating vs prior window", observed=flow.volume_acceleration,
            )

        # --- Price -------------------------------------------------------- #
        pm = flow.price_momentum
        if pm >= PRICE_MOVE_CRITICAL:
            add(AnomalyType.PRICE_SPIKE, AnomalySeverity.CRITICAL, f"+{pm*100:.1f}% over 5m", PRICE_MOVE_CRITICAL, pm)
        elif pm >= PRICE_MOVE_SPIKE:
            add(AnomalyType.PRICE_SPIKE, AnomalySeverity.HIGH, f"+{pm*100:.1f}% over 5m", PRICE_MOVE_SPIKE, pm)
        elif pm <= -PRICE_MOVE_CRITICAL:
            add(AnomalyType.PRICE_DROP, AnomalySeverity.CRITICAL, f"{pm*100:.1f}% over 5m", -PRICE_MOVE_CRITICAL, pm)
        elif pm <= -PRICE_MOVE_SPIKE:
            add(AnomalyType.PRICE_DROP, AnomalySeverity.HIGH, f"{pm*100:.1f}% over 5m", -PRICE_MOVE_SPIKE, pm)

        # --- Flow acceleration ------------------------------------------- #
        if flow.flow_acceleration > 0 and abs(flow.flow_acceleration) > abs(flow.flow_15m) * 0.5 + 1:
            add(AnomalyType.FLOW_ACCELERATION, AnomalySeverity.MEDIUM, "money-flow proxy accelerating", observed=flow.flow_acceleration)

        # --- Structure ---------------------------------------------------- #
        if intraday_high is not None and price >= intraday_high:
            add(AnomalyType.NEW_INTRADAY_HIGH, AnomalySeverity.MEDIUM, f"new intraday high {price}", intraday_high, price)
            if pm > 0:
                add(AnomalyType.BREAKOUT, AnomalySeverity.HIGH, "breakout above intraday high on positive momentum", intraday_high, price)
        if intraday_low is not None and price <= intraday_low:
            add(AnomalyType.NEW_INTRADAY_LOW, AnomalySeverity.MEDIUM, f"new intraday low {price}", intraday_low, price)
            if pm < 0:
                add(AnomalyType.BREAKDOWN, AnomalySeverity.HIGH, "breakdown below intraday low on negative momentum", intraday_low, price)

        # --- Price/volume divergence ------------------------------------- #
        if pm > PRICE_MOVE_SPIKE and flow.flow_5m < 0:
            add(AnomalyType.PRICE_VOLUME_DIVERGENCE, AnomalySeverity.MEDIUM, "price up but signed flow negative", observed=flow.flow_5m)
        elif pm < -PRICE_MOVE_SPIKE and flow.flow_5m > 0:
            add(AnomalyType.PRICE_VOLUME_DIVERGENCE, AnomalySeverity.MEDIUM, "price down but signed flow positive", observed=flow.flow_5m)

        # --- Unusual activity (composite) -------------------------------- #
        if r5 >= VOLUME_SPIKE_RATIO and abs(pm) >= PRICE_MOVE_SPIKE:
            add(AnomalyType.UNUSUAL_ACTIVITY, AnomalySeverity.HIGH, f"volume {r5:.1f}x + {pm*100:.1f}% move", observed=r5)

        return out
