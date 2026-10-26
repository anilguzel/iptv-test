"""Seed the default watchlist (KTLEV, THYAO, ASELS, TUPRS, EREGL)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import models
from .repository import ensure_stock


def seed_watchlist(session: Session, symbols: list[str] | None = None) -> list[str]:
    symbols = symbols or get_settings().default_symbols
    for symbol in symbols:
        ensure_stock(session, symbol)
        exists = session.scalar(
            select(models.Watchlist).where(models.Watchlist.user_id.is_(None), models.Watchlist.symbol == symbol)
        )
        if not exists:
            session.add(models.Watchlist(user_id=None, symbol=symbol))
    return symbols
