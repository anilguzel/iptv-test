"""Signal-engine worker.

Polls the market-data provider on an interval, ingests/validates ticks and
recomputes signals for every watchlist symbol via the shared runner.
"""
from __future__ import annotations

import asyncio
import logging
import signal as signalmod

from bist_core.config import get_settings
from bist_core.db import init_db, models, session_scope
from bist_core.providers.factory import get_market_data_provider, get_news_provider
from bist_core.runner import run_cycle
from bist_core.seed import seed_watchlist
from sqlalchemy import select

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("signal_engine")


def _watchlist() -> list[str]:
    with session_scope() as session:
        rows = session.scalars(select(models.Watchlist.symbol).where(models.Watchlist.user_id.is_(None))).all()
        return list(rows) or get_settings().default_symbols


async def main() -> None:
    settings = get_settings()
    init_db()
    with session_scope() as session:
        seed_watchlist(session)

    provider = get_market_data_provider(settings)
    news = get_news_provider(settings)
    stop = asyncio.Event()

    def _handle(*_):
        log.info("shutdown requested")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signalmod.SIGINT, signalmod.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle)
        except NotImplementedError:  # pragma: no cover (non-unix)
            pass

    log.info("signal-engine started (provider=%s, interval=%ss)", provider.name, settings.signal_interval_seconds)
    try:
        while not stop.is_set():
            symbols = _watchlist()
            with session_scope() as session:
                payloads = await run_cycle(session, provider, news, symbols)
            log.info("cycle complete: %d symbols scored", len(payloads))
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.signal_interval_seconds)
            except TimeoutError:
                pass
    finally:
        await provider.aclose()
        log.info("signal-engine stopped")


if __name__ == "__main__":
    asyncio.run(main())
