"""FastAPI application: dashboard, stock detail, critical moves, backtest, AI.

Delayed data is preserved end-to-end: every quote/signal carries its
``data_status`` so the UI can label DELAYED / STALE / DEMO and never fake LIVE.
"""
from __future__ import annotations

from datetime import UTC, datetime

from bist_core.ai import get_ai_analyzer
from bist_core.config import get_settings
from bist_core.db import get_session, init_db, models, session_scope
from bist_core.engines.backtest import BacktestEngine, BacktestSignal, PricePoint
from bist_core.providers.factory import get_market_data_provider, get_news_provider
from bist_core.repository import recent_history
from bist_core.runner import run_cycle
from bist_core.schemas import ScoreResult
from bist_core.seed import seed_watchlist
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    with session_scope() as session:
        seed_watchlist(session)


# --------------------------------------------------------------------------- #
# Response models                                                             #
# --------------------------------------------------------------------------- #
class WatchlistRow(BaseModel):
    symbol: str
    price: float | None = None
    change_percent: float | None = None
    volume_ratio_5m: float | None = None
    flow_5m: float | None = None
    flow_15m: float | None = None
    score: float | None = None
    direction: str | None = None
    data_status: str | None = None
    last_alert: datetime | None = None


class AddSymbol(BaseModel):
    symbol: str


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def _latest_signal(session: Session, symbol: str) -> models.Signal | None:
    return session.scalar(
        select(models.Signal)
        .where(models.Signal.symbol == symbol.upper())
        .order_by(models.Signal.timestamp.desc())
        .limit(1)
    )


def _latest_tick(session: Session, symbol: str) -> models.MarketTick | None:
    return session.scalar(
        select(models.MarketTick)
        .where(models.MarketTick.symbol == symbol.upper())
        .order_by(models.MarketTick.market_timestamp.desc())
        .limit(1)
    )


def _watchlist_symbols(session: Session) -> list[str]:
    rows = session.scalars(select(models.Watchlist.symbol).where(models.Watchlist.user_id.is_(None))).all()
    return list(rows) or settings.default_symbols


# --------------------------------------------------------------------------- #
# Routes                                                                      #
# --------------------------------------------------------------------------- #
@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "provider": "demo" if settings.demo_mode else settings.market_data_provider,
        "demo_mode": settings.demo_mode,
        "time": datetime.now(UTC).isoformat(),
    }


@app.get("/watchlist", response_model=list[WatchlistRow])
def get_watchlist(session: Session = Depends(get_session)) -> list[WatchlistRow]:
    rows: list[WatchlistRow] = []
    for symbol in _watchlist_symbols(session):
        tick = _latest_tick(session, symbol)
        sig = _latest_signal(session, symbol)
        snap = (sig.data_snapshot or {}) if sig else {}
        flow = snap.get("flow", {})
        vol = snap.get("volume", {})
        rows.append(
            WatchlistRow(
                symbol=symbol,
                price=tick.price if tick else None,
                change_percent=tick.change_percent if tick else None,
                volume_ratio_5m=vol.get("volume_ratio_5m"),
                flow_5m=flow.get("flow_5m"),
                flow_15m=flow.get("flow_15m"),
                score=sig.score if sig else None,
                direction=sig.direction if sig else None,
                data_status=(tick.data_status if tick else None),
            )
        )
    return rows


@app.post("/watchlist")
def add_symbol(body: AddSymbol, session: Session = Depends(get_session)) -> dict:
    symbol = body.symbol.strip().upper()
    if not symbol.isalnum():
        raise HTTPException(400, "invalid symbol")
    exists = session.scalar(
        select(models.Watchlist).where(models.Watchlist.user_id.is_(None), models.Watchlist.symbol == symbol)
    )
    if not exists:
        session.add(models.Watchlist(user_id=None, symbol=symbol))
        session.commit()
    return {"symbol": symbol, "added": not exists}


@app.delete("/watchlist/{symbol}")
def remove_symbol(symbol: str, session: Session = Depends(get_session)) -> dict:
    symbol = symbol.upper()
    row = session.scalar(
        select(models.Watchlist).where(models.Watchlist.user_id.is_(None), models.Watchlist.symbol == symbol)
    )
    if row:
        session.delete(row)
        session.commit()
    return {"symbol": symbol, "removed": bool(row)}


@app.get("/stocks/{symbol}")
def stock_detail(symbol: str, session: Session = Depends(get_session)) -> dict:
    symbol = symbol.upper()
    tick = _latest_tick(session, symbol)
    sig = _latest_signal(session, symbol)
    history = recent_history(session, symbol)
    news = session.scalars(
        select(models.NewsEventRow).where(models.NewsEventRow.symbol == symbol).order_by(models.NewsEventRow.timestamp.desc()).limit(10)
    ).all()
    timeline = session.scalars(
        select(models.Signal).where(models.Signal.symbol == symbol).order_by(models.Signal.timestamp.desc()).limit(50)
    ).all()
    snap = (sig.data_snapshot or {}) if sig else {}
    return {
        "symbol": symbol,
        "quote": {
            "price": tick.price if tick else None,
            "change_percent": tick.change_percent if tick else None,
            "volume": tick.volume if tick else None,
            "data_status": tick.data_status if tick else None,
            "provider": tick.provider if tick else None,
            "market_timestamp": tick.market_timestamp.isoformat() if tick else None,
            "received_at": tick.received_at.isoformat() if tick else None,
            "latency": tick.latency if tick else None,
        },
        "signal": None
        if not sig
        else {
            "score": sig.score,
            "direction": sig.direction,
            "confidence": sig.confidence,
            "change": sig.change,
            "evidence": sig.evidence,
            "risks": sig.risks,
            "invalidation_conditions": sig.invalidation_conditions,
            "data_status": sig.data_status,
            "timestamp": sig.timestamp.isoformat(),
        },
        "flow": snap.get("flow", {}),
        "volume": snap.get("volume", {}),
        "technical": snap.get("technical", {}),
        "anomalies": snap.get("anomalies", []),
        "history": [
            {"timestamp": b.timestamp.isoformat(), "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}
            for b in history
        ],
        "signal_timeline": [
            {"timestamp": s.timestamp.isoformat(), "score": s.score, "direction": s.direction, "change": s.change}
            for s in reversed(timeline)
        ],
        "news": [
            {"timestamp": n.timestamp.isoformat(), "headline": n.headline, "category": n.category, "importance": n.importance}
            for n in news
        ],
    }


@app.get("/stocks/{symbol}/ai")
def stock_ai(symbol: str, session: Session = Depends(get_session)) -> dict:
    symbol = symbol.upper()
    sig = _latest_signal(session, symbol)
    tick = _latest_tick(session, symbol)
    if not sig or not tick:
        return {"summary": "data_unavailable"}

    # Reconstruct a ScoreResult from the stored snapshot so the explainer runs
    # on exactly the data that produced the signal.
    snap = sig.data_snapshot or {}
    score = ScoreResult(
        score=sig.score,
        direction=sig.direction,
        confidence=sig.confidence,
        components=[],
        scoring_version=sig.scoring_version,
        data_snapshot=snap,
    )
    news = session.scalars(select(models.NewsEventRow).where(models.NewsEventRow.symbol == symbol)).all()
    analyzer = get_ai_analyzer()
    analysis = analyzer.analyze(symbol=symbol, price=tick.price, score=score, news=[n.headline for n in news])
    return analysis.model_dump()


@app.get("/critical-moves")
def critical_moves(session: Session = Depends(get_session), limit: int = 50) -> list[dict]:
    rows = session.scalars(
        select(models.Signal)
        .where(models.Signal.change.in_(["SIGNAL_STRENGTHENING", "SIGNAL_WEAKENING", "SIGNAL_REVERSAL"]))
        .order_by(models.Signal.timestamp.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": s.id,
            "timestamp": s.timestamp.isoformat(),
            "symbol": s.symbol,
            "score": s.score,
            "direction": s.direction,
            "change": s.change,
            "evidence": s.evidence,
            "data_snapshot": s.data_snapshot,  # clicking an event shows the exact snapshot
        }
        for s in rows
    ]


@app.get("/backtest/{symbol}")
def backtest(symbol: str, session: Session = Depends(get_session), horizon: int = 30) -> dict:
    symbol = symbol.upper()
    sig_rows = session.scalars(
        select(models.Signal).where(models.Signal.symbol == symbol).order_by(models.Signal.timestamp.asc())
    ).all()
    tick_rows = session.scalars(
        select(models.MarketTick).where(models.MarketTick.symbol == symbol).order_by(models.MarketTick.market_timestamp.asc())
    ).all()
    if not sig_rows or not tick_rows:
        return {"signal_count": 0, "note": "insufficient stored signals/prices for backtest"}

    signals = [BacktestSignal(timestamp=s.timestamp, symbol=symbol, direction=s.direction, score=s.score) for s in sig_rows]
    prices = {symbol: [PricePoint(timestamp=t.market_timestamp, price=t.price) for t in tick_rows]}
    report = BacktestEngine(primary_horizon=horizon).run(signals, prices)
    return {
        "symbol": symbol,
        "horizon_minutes": horizon,
        "signal_count": report.signal_count,
        "win_rate": report.win_rate,
        "average_return": report.average_return,
        "median_return": report.median_return,
        "max_drawdown": report.max_drawdown,
        "profit_factor": None if report.profit_factor == float("inf") else report.profit_factor,
    }


@app.post("/refresh")
async def refresh(session: Session = Depends(get_session)) -> dict:
    """Run one collection+scoring cycle immediately (handy for demo/dev)."""
    provider = get_market_data_provider(settings)
    news = get_news_provider(settings)
    symbols = _watchlist_symbols(session)
    try:
        payloads = await run_cycle(session, provider, news, symbols)
    finally:
        await provider.aclose()
    return {"updated": [p.symbol for p in payloads], "count": len(payloads)}
