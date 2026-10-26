"""Persistence helpers bridging provider DTOs, engines and ORM rows."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import models
from .schemas import OhlcvBar, Quote, SignalPayload, Tick


def ensure_stock(session: Session, symbol: str, name: str | None = None) -> models.Stock:
    symbol = symbol.upper()
    stock = session.scalar(select(models.Stock).where(models.Stock.symbol == symbol))
    if stock is None:
        stock = models.Stock(symbol=symbol, name=name)
        session.add(stock)
        session.flush()
    return stock


def save_tick(session: Session, quote: Quote) -> models.MarketTick:
    ensure_stock(session, quote.symbol)
    tick = models.MarketTick(
        symbol=quote.symbol.upper(),
        price=quote.price,
        volume=quote.volume,
        change_percent=quote.change_percent,
        provider=quote.provider,
        data_status=quote.data_status.value,
        market_timestamp=quote.timestamp,
        latency=quote.latency,
    )
    session.add(tick)
    return tick


def save_ohlcv(session: Session, bars: list[OhlcvBar], interval: str = "1d") -> int:
    saved = 0
    for bar in bars:
        exists = session.scalar(
            select(models.Ohlcv).where(
                models.Ohlcv.symbol == bar.symbol.upper(),
                models.Ohlcv.interval == interval,
                models.Ohlcv.timestamp == bar.timestamp,
            )
        )
        if exists:
            continue
        session.add(
            models.Ohlcv(
                symbol=bar.symbol.upper(),
                interval=interval,
                timestamp=bar.timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
        )
        saved += 1
    return saved


def recent_ticks(session: Session, symbol: str, *, minutes: int = 120) -> list[Tick]:
    since = datetime.now(UTC) - timedelta(minutes=minutes)
    rows = session.scalars(
        select(models.MarketTick)
        .where(models.MarketTick.symbol == symbol.upper(), models.MarketTick.market_timestamp >= since)
        .order_by(models.MarketTick.market_timestamp.asc())
    ).all()
    return [Tick(timestamp=r.market_timestamp, price=r.price, volume=r.volume) for r in rows]


def recent_history(session: Session, symbol: str, *, limit: int = 60) -> list[OhlcvBar]:
    rows = session.scalars(
        select(models.Ohlcv)
        .where(models.Ohlcv.symbol == symbol.upper(), models.Ohlcv.interval == "1d")
        .order_by(models.Ohlcv.timestamp.asc())
        .limit(limit)
    ).all()
    return [
        OhlcvBar(symbol=r.symbol, timestamp=r.timestamp, open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume)
        for r in rows
    ]


def last_signal_score(session: Session, symbol: str) -> float | None:
    row = session.scalar(
        select(models.Signal)
        .where(models.Signal.symbol == symbol.upper())
        .order_by(models.Signal.timestamp.desc())
        .limit(1)
    )
    return row.score if row else None


def save_signal(session: Session, payload: SignalPayload, scoring_version: str = "1.0.0") -> models.Signal:
    ensure_stock(session, payload.symbol)
    row = models.Signal(
        symbol=payload.symbol.upper(),
        timestamp=payload.timestamp,
        score=payload.score,
        direction=payload.direction.value,
        confidence=payload.confidence,
        change=payload.change.value,
        data_status=payload.data_status.value,
        evidence=payload.evidence,
        risks=payload.risks,
        invalidation_conditions=payload.invalidation_conditions,
        data_snapshot=payload.data_snapshot,
        scoring_version=scoring_version,
    )
    session.add(row)
    session.flush()
    return row


def save_flow_snapshot(session: Session, symbol: str, timestamp: datetime, metrics: dict) -> None:
    session.add(models.FlowSnapshot(symbol=symbol.upper(), timestamp=timestamp, metrics=metrics))


def save_news(session: Session, events) -> int:
    """Persist news events, de-duplicated on (symbol, timestamp, headline)."""
    saved = 0
    for ev in events:
        exists = session.scalar(
            select(models.NewsEventRow).where(
                models.NewsEventRow.symbol == ev.symbol.upper(),
                models.NewsEventRow.timestamp == ev.timestamp,
                models.NewsEventRow.headline == ev.headline,
            )
        )
        if exists:
            continue
        session.add(
            models.NewsEventRow(
                symbol=ev.symbol.upper(),
                timestamp=ev.timestamp,
                headline=ev.headline,
                category=ev.category.value,
                importance=ev.importance,
                source=ev.source,
            )
        )
        saved += 1
    return saved
