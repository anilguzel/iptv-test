"""Collection + scoring cycle, shared by the signal-engine worker and the API.

One cycle: fetch quotes for the watchlist, validate, persist ticks, (re)load
recent ticks + daily history, assemble a signal, and persist it when the change
is material. Daily OHLCV history is refreshed opportunistically.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .engines.signal_change import is_material
from .pipeline import SignalPipeline
from .providers.base import MarketDataProvider, NewsProvider
from .repository import (
    last_signal_score,
    recent_history,
    recent_ticks,
    save_flow_snapshot,
    save_news,
    save_ohlcv,
    save_signal,
    save_tick,
)
from .schemas import SignalPayload
from .validation import ValidationError, validate_quote

log = logging.getLogger("bist_core.runner")


async def ensure_history(session: Session, provider: MarketDataProvider, symbol: str) -> None:
    """Fetch & store daily history if we don't have enough yet."""
    if len(recent_history(session, symbol, limit=25)) >= 20:
        return
    try:
        bars = await provider.get_history(symbol, interval="1d", limit=120)
        save_ohlcv(session, bars)
    except Exception as exc:
        log.warning("history fetch failed for %s: %s", symbol, exc)


async def run_cycle(
    session: Session,
    provider: MarketDataProvider,
    news_provider: NewsProvider,
    symbols: list[str],
    *,
    pipeline: SignalPipeline | None = None,
    known_symbols: set[str] | None = None,
) -> list[SignalPayload]:
    pipeline = pipeline or SignalPipeline()
    known = known_symbols or {s.upper() for s in symbols}
    payloads: list[SignalPayload] = []

    try:
        quotes = await provider.get_quotes(symbols)
    except Exception as exc:
        log.error("provider get_quotes failed: %s", exc)
        return payloads

    for quote in quotes:
        try:
            validate_quote(quote, known_symbols=known)
        except ValidationError as exc:
            log.warning("dropping invalid quote: %s", exc)
            continue

        save_tick(session, quote)
        await ensure_history(session, provider, quote.symbol)

        ticks = recent_ticks(session, quote.symbol, minutes=120)
        history = recent_history(session, quote.symbol)
        try:
            news = await news_provider.get_news(quote.symbol)
            save_news(session, news)
        except Exception:
            news = []

        prev = last_signal_score(session, quote.symbol)
        score, _anomalies, payload = pipeline.assemble(
            quote=quote, ticks=ticks, history=history, news=news, previous_score=prev
        )
        save_flow_snapshot(session, quote.symbol, quote.timestamp, score.data_snapshot.get("flow", {}))

        if is_material(prev, payload.score):
            save_signal(session, payload, scoring_version=score.scoring_version)
        payloads.append(payload)

    session.commit()
    return payloads
