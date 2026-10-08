"""Backtest / signal-outcome engine.

For every signal it computes forward returns (5/15/30/60m), MFE and MAE, then
aggregates win rate, mean/median return, max drawdown and profit factor.

Look-ahead bias is structurally prevented: the entry price is the last price
known AT the signal timestamp, and forward prices are taken strictly AFTER it.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta

HORIZONS_MIN = (5, 15, 30, 60)


@dataclass
class BacktestSignal:
    timestamp: datetime
    symbol: str
    direction: str  # SignalDirection value
    score: float


@dataclass
class PricePoint:
    timestamp: datetime
    price: float


@dataclass
class SignalOutcome:
    symbol: str
    timestamp: datetime
    direction: str
    score: float
    entry_price: float
    returns: dict[int, float] = field(default_factory=dict)  # horizon_min -> signed return
    mfe: float = 0.0
    mae: float = 0.0


@dataclass
class BacktestReport:
    signal_count: int = 0
    win_rate: float = 0.0
    average_return: float = 0.0
    median_return: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    outcomes: list[SignalOutcome] = field(default_factory=list)


def _direction_sign(direction: str) -> int:
    if direction in ("POSITIVE", "STRONG_POSITIVE", "EXTREME_POSITIVE"):
        return 1
    if direction in ("NEGATIVE", "STRONG_NEGATIVE"):
        return -1
    return 0  # NEUTRAL / WATCH -> not traded


class BacktestEngine:
    def __init__(self, primary_horizon: int = 30):
        self.primary_horizon = primary_horizon

    def _entry_price(self, prices: list[PricePoint], at: datetime) -> float | None:
        known = [p for p in prices if p.timestamp <= at]
        return known[-1].price if known else None

    def evaluate_signal(self, signal: BacktestSignal, prices: list[PricePoint]) -> SignalOutcome | None:
        sign = _direction_sign(signal.direction)
        prices = sorted(prices, key=lambda p: p.timestamp)
        entry = self._entry_price(prices, signal.timestamp)
        if entry is None or entry <= 0 or sign == 0:
            return None

        outcome = SignalOutcome(
            symbol=signal.symbol,
            timestamp=signal.timestamp,
            direction=signal.direction,
            score=signal.score,
            entry_price=entry,
        )
        # Forward window = strictly after the signal, up to the longest horizon.
        max_h = max(HORIZONS_MIN)
        forward = [p for p in prices if signal.timestamp < p.timestamp <= signal.timestamp + timedelta(minutes=max_h)]

        for h in HORIZONS_MIN:
            cutoff = signal.timestamp + timedelta(minutes=h)
            window = [p for p in forward if p.timestamp <= cutoff]
            if window:
                raw = (window[-1].price - entry) / entry
                outcome.returns[h] = round(raw * sign, 6)

        if forward:
            excursions = [(p.price - entry) / entry * sign for p in forward]
            outcome.mfe = round(max(excursions), 6)
            outcome.mae = round(min(excursions), 6)
        return outcome

    def run(self, signals: list[BacktestSignal], prices_by_symbol: dict[str, list[PricePoint]]) -> BacktestReport:
        outcomes: list[SignalOutcome] = []
        for sig in signals:
            series = prices_by_symbol.get(sig.symbol, [])
            outcome = self.evaluate_signal(sig, series)
            if outcome and self.primary_horizon in outcome.returns:
                outcomes.append(outcome)

        if not outcomes:
            return BacktestReport()

        rets = [o.returns[self.primary_horizon] for o in outcomes]
        wins = [r for r in rets if r > 0]
        losses = [r for r in rets if r < 0]
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))

        # Max drawdown of the cumulative equity curve (sum of returns).
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for r in rets:
            equity += r
            peak = max(peak, equity)
            max_dd = min(max_dd, equity - peak)

        return BacktestReport(
            signal_count=len(outcomes),
            win_rate=round(len(wins) / len(outcomes), 4),
            average_return=round(statistics.fmean(rets), 6),
            median_return=round(statistics.median(rets), 6),
            max_drawdown=round(max_dd, 6),
            profit_factor=round(gross_win / gross_loss, 4) if gross_loss > 0 else float("inf"),
            outcomes=outcomes,
        )
