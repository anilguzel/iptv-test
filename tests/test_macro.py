from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import httpx
from bist_core.config import Settings
from bist_core.enums import DataStatus
from bist_core.providers.evds import EvdsMacroProvider, build_snapshot, series_name
from bist_core.providers.factory import get_macro_provider
from bist_core.providers.macro_demo import DemoMacroProvider
from bist_core.schemas import MacroSeriesPoint

_ITEMS = {
    "items": [
        {"Tarih": "01-01-2024", "TP_DK_USD_A": "30.0", "TP_DK_EUR_A": "33.0"},
        {"Tarih": "02-01-2024", "TP_DK_USD_A": "31.5", "TP_DK_EUR_A": ""},  # EUR missing
        {"Tarih": "03-01-2024", "TP_DK_USD_A": "33.0", "TP_DK_EUR_A": "34.0"},
    ]
}


def _evds_with_canned_response() -> EvdsMacroProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        # EVDS puts series/params after the path with no '?'; just assert it is present.
        assert "series=" in str(request.url)
        return httpx.Response(200, json=_ITEMS)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return EvdsMacroProvider(Settings(EVDS_API_KEY="dummy"), client=client)


def test_evds_parses_series_and_computes_change():
    prov = _evds_with_canned_response()
    snaps = asyncio.run(prov.get_series(["TP.DK.USD.A", "TP.DK.EUR.A"], start=date(2024, 1, 1), end=date(2024, 1, 3)))
    asyncio.run(prov.aclose())
    by = {s.series_code: s for s in snaps}

    usd = by["TP.DK.USD.A"]
    assert usd.latest_value == 33.0
    assert usd.previous_value == 31.5
    assert round(usd.change_percent, 2) == 4.76
    assert usd.as_of == date(2024, 1, 3)
    assert usd.name == "USD/TRY (alış)"

    # EUR skipped the empty value entirely (never fabricated).
    eur = by["TP.DK.EUR.A"]
    assert [p.date for p in eur.points] == [date(2024, 1, 1), date(2024, 1, 3)]
    assert eur.latest_value == 34.0


def test_evds_old_data_is_stale():
    prov = _evds_with_canned_response()
    snaps = asyncio.run(prov.get_latest(["TP.DK.USD.A"]))
    asyncio.run(prov.aclose())
    # The canned dates are in 2024, far older than MACRO_STALE_DAYS.
    assert snaps[0].data_status == DataStatus.STALE


def test_build_snapshot_fresh_is_delayed_not_live():
    today = datetime.now(UTC).date()
    pts = [MacroSeriesPoint(series_code="TP.DK.USD.A", date=today, value=34.0)]
    snap = build_snapshot("TP.DK.USD.A", pts, provider="evds", now=today)
    assert snap.data_status == DataStatus.DELAYED  # never LIVE for EVDS


def test_demo_macro_is_deterministic_and_demo():
    prov = DemoMacroProvider()
    a = asyncio.run(prov.get_latest(["TP.DK.USD.A", "TP.DK.EUR.A"]))
    b = asyncio.run(prov.get_latest(["TP.DK.USD.A", "TP.DK.EUR.A"]))
    assert a[0].data_status == DataStatus.DEMO
    assert a[0].latest_value == b[0].latest_value  # deterministic
    assert a[0].latest_value and a[0].latest_value > 0


def test_factory_demo_mode_forces_demo_macro():
    assert isinstance(get_macro_provider(Settings(DEMO_MODE=True, MACRO_PROVIDER="evds")), DemoMacroProvider)


def test_factory_can_disable_macro():
    assert get_macro_provider(Settings(DEMO_MODE=False, MACRO_PROVIDER="none")) is None


def test_series_name_fallback():
    assert series_name("TP.UNKNOWN.CODE") == "TP.UNKNOWN.CODE"
