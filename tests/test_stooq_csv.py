from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
import pytest
from bist_core.config import Settings
from bist_core.providers.csv_ohlcv import CsvDataError, parse_ohlcv_csv
from bist_core.providers.stooq import StooqProvider
from bist_core.research.data import detect_jumps
from bist_core.schemas import OhlcvBar

STOOQ_CSV = """Date,Open,High,Low,Close,Volume
2025-01-02,1.10,1.20,1.00,1.15,120000
2025-01-03,1.15,1.30,1.10,1.25,98000
"""

YAHOO_CSV = """Date,Open,High,Low,Close,Adj Close,Volume
2025-01-02,10,11,9,10,5,1000
2025-01-03,10,12,10,11,5.5,1200
"""


def test_parse_stooq_csv():
    bars = parse_ohlcv_csv(STOOQ_CSV, "smtk")
    assert [b.close for b in bars] == [1.15, 1.25]
    assert bars[0].symbol == "SMTK" and bars[1].volume == 98000


def test_yahoo_adj_close_rescales_all_prices():
    bars = parse_ohlcv_csv(YAHOO_CSV, "X")
    # factor = adj/close = 0.5 on both days (e.g. after a 2:1 split)
    assert bars[0].close == pytest.approx(5.0) and bars[0].high == pytest.approx(5.5)
    assert bars[1].close == pytest.approx(5.5)


def test_non_csv_response_raises_clear_error():
    with pytest.raises(CsvDataError, match="not an OHLCV CSV"):
        parse_ohlcv_csv("No data", "ZZZZ")


def test_rows_without_close_are_skipped():
    bars = parse_ohlcv_csv("Date,Open,High,Low,Close,Volume\n2025-01-02,1,1,1,,5\n2025-01-03,1,1,1,1.1,5\n", "X")
    assert len(bars) == 1


def test_stooq_symbol_mapping():
    p = StooqProvider(Settings())
    assert p.stooq_symbol("SMTK") == "smtk.us"
    assert p.stooq_symbol("iwm.us") == "iwm.us"
    assert p.stooq_symbol("^SPX") == "^spx"


def test_stooq_get_history_requests_daily_csv():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(dict(req.url.params))
        seen["path"] = req.url.path
        return httpx.Response(200, text=STOOQ_CSV)

    s = Settings()
    p = StooqProvider(s, client=httpx.AsyncClient(base_url=s.stooq_base_url, transport=httpx.MockTransport(handler)))
    bars = asyncio.run(p.get_history("SMTK", period="5y"))
    asyncio.run(p.aclose())
    assert seen == {"s": "smtk.us", "i": "d", "path": "/q/d/l/"}
    assert len(bars) == 2


def test_detect_jumps_flags_split_like_moves():
    def bar(day: int, close: float) -> OhlcvBar:
        return OhlcvBar(symbol="X", timestamp=datetime(2025, 1, day, tzinfo=UTC), open=close, high=close,
                        low=close, close=close, volume=1)

    jumps = detect_jumps({"X": [bar(2, 1.0), bar(3, 1.05), bar(6, 10.5)]})  # 1:10 reverse split look
    assert len(jumps) == 1 and jumps[0]["date"] == "2025-01-06"


def test_nasdaq_com_export_format():
    text = (
        "Date,Close/Last,Volume,Open,High,Low\n"
        "01/03/2025,$1.25,98000,$1.15,$1.30,$1.10\n"
        "01/02/2025,$1.15,120000,$1.10,$1.20,$1.00\n"
    )
    bars = parse_ohlcv_csv(text, "SMTK")
    assert [b.timestamp.date().isoformat() for b in bars] == ["2025-01-02", "2025-01-03"]  # sorted ascending
    assert bars[1].close == 1.25 and bars[1].high == 1.30 and bars[0].volume == 120000
