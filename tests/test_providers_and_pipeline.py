from __future__ import annotations

import asyncio

from bist_core.enums import DataStatus
from bist_core.pipeline import SignalPipeline
from bist_core.providers.demo import DemoMarketDataProvider
from conftest import make_ticks


def test_demo_provider_is_deterministic_and_flagged_demo():
    provider = DemoMarketDataProvider()
    q1 = asyncio.run(provider.get_quote("KTLEV"))
    q2 = asyncio.run(provider.get_quote("KTLEV"))
    assert q1.data_status == DataStatus.DEMO
    assert q1.provider == "demo"
    # Same minute bucket -> identical price (deterministic).
    assert q1.price == q2.price
    assert q1.price > 0


def test_demo_quotes_batch():
    provider = DemoMarketDataProvider()
    quotes = asyncio.run(provider.get_quotes(["KTLEV", "THYAO", "ASELS"]))
    assert {q.symbol for q in quotes} == {"KTLEV", "THYAO", "ASELS"}


def test_pipeline_assembles_signal_with_snapshot():
    provider = DemoMarketDataProvider()
    quote = asyncio.run(provider.get_quote("KTLEV"))
    # Build a rising tick series.
    prices = [quote.price * (1 + 0.001 * i) for i in range(40)]
    volumes = [1000.0 * i for i in range(40)]
    ticks = make_ticks(prices, volumes)

    _score, _anomalies, payload = SignalPipeline().assemble(quote=quote, ticks=ticks)
    assert 0 <= payload.score <= 100
    assert payload.symbol == "KTLEV"
    # Snapshot must make the signal reconstructable.
    assert "flow" in payload.data_snapshot
    assert "component_norms" in payload.data_snapshot
    assert payload.data_status == DataStatus.DEMO
