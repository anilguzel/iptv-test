from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from bist_core.automation import jobs as jobs_mod
from bist_core.automation.__main__ import main as automation_main
from bist_core.config import Settings
from bist_core.providers.yahoo import USER_AGENT, YahooChartProvider, YahooDataError, parse_chart, period_bounds

# 2025-01-02 and 2025-01-03 14:30 UTC (Istanbul is UTC+3 -> same trading date)
CHART = {"chart": {"error": None, "result": [{
    "meta": {"gmtoffset": 10800},
    "timestamp": [1735828200, 1735914600, 1736001000],
    "indicators": {
        "quote": [{"open": [10, 11, None], "high": [11, 12, None], "low": [9, 10, None],
                   "close": [10, 12, None], "volume": [1000, 2000, None]}],
        "adjclose": [{"adjclose": [5, 6, None]}],
    },
}]}}


def test_parse_chart_adjusts_and_skips_empty_days():
    bars = parse_chart(CHART, "thyao")
    assert [b.timestamp.date().isoformat() for b in bars] == ["2025-01-02", "2025-01-03"]
    assert bars[0].symbol == "THYAO"
    assert bars[0].close == pytest.approx(5) and bars[0].high == pytest.approx(5.5)  # factor 0.5
    assert bars[1].volume == 2000


def test_parse_chart_error_raises():
    with pytest.raises(YahooDataError, match="Not Found"):
        parse_chart({"chart": {"result": None, "error": {"code": "Not Found", "description": "No data"}}}, "ZZZ")


def test_symbol_suffix_mapping():
    p = YahooChartProvider(Settings(), suffix=".IS")
    assert p.yahoo_symbol("thyao") == "THYAO.IS"
    assert p.yahoo_symbol("XU100") == "XU100.IS"
    assert p.yahoo_symbol("BRK.B") == "BRK.B" and p.yahoo_symbol("^GSPC") == "^GSPC"


def test_provider_request_and_http_error():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"], seen["params"], seen["ua"] = req.url.path, dict(req.url.params), req.headers["user-agent"]
        if "ZZZ" in req.url.path:
            return httpx.Response(429, text="Too Many Requests")
        return httpx.Response(200, json=CHART)

    s = Settings()
    client = httpx.AsyncClient(base_url=s.yahoo_base_url, headers={"User-Agent": USER_AGENT},
                               transport=httpx.MockTransport(handler))
    p = YahooChartProvider(s, suffix=".IS", client=client)
    bars = asyncio.run(p.get_history("THYAO", period="5y"))
    assert seen["path"] == "/v8/finance/chart/THYAO.IS" and "range" not in seen["params"]
    assert int(seen["params"]["period2"]) - int(seen["params"]["period1"]) == 1827 * 86400  # 5y, explicit bounds
    assert seen["ua"] == USER_AGENT and len(bars) == 2
    with pytest.raises(YahooDataError, match="HTTP 429"):
        asyncio.run(p.get_history("ZZZ", period="5y"))


class _Fake:
    name = "fake"

    def __init__(self, ok: bool):
        self.ok = ok

    async def get_history(self, symbol, *, interval="1d", limit=120, period=None):
        if not self.ok:
            raise RuntimeError("blocked")
        return parse_chart(CHART, symbol)

    async def aclose(self):
        return None


def test_probe_reports_each_source(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(jobs_mod, "make_provider", lambda source, suffix="": _Fake(ok=source == "yahoo"))
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    cfg = tmp_path / "probe.json"
    cfg.write_text(json.dumps({"collect": [
        {"source": "stooq", "universe": "SMTK", "dir": "s"},
        {"source": "yahoo", "universe": "THYAO", "suffix": ".IS", "dir": "y"},
    ]}))
    assert automation_main(["probe", "--config", str(cfg)]) == 0
    out = capsys.readouterr().out
    assert "| stooq | SMTK | FAILED: RuntimeError: blocked |" in out
    assert "| yahoo (.IS) | THYAO | ok: 2 bars, 2025-01-02 -> 2025-01-03 |" in out
    assert "Data source probe" in summary.read_text()


def test_probe_fails_when_nothing_works(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_mod, "make_provider", lambda source, suffix="": _Fake(ok=False))
    cfg = tmp_path / "probe.json"
    cfg.write_text(json.dumps({"collect": [{"source": "stooq", "universe": "SMTK"}]}))
    assert automation_main(["probe", "--config", str(cfg)]) == 1


def test_monthly_bars_are_rejected():
    # What Yahoo returns for range=max: one bar per month despite interval=1d.
    stamps = [1704067200 + i * 31 * 86400 for i in range(6)]
    monthly = {"chart": {"error": None, "result": [{"meta": {"gmtoffset": 0}, "timestamp": stamps,
               "indicators": {"quote": [{"open": [1] * 6, "high": [1] * 6, "low": [1] * 6,
                                         "close": [1] * 6, "volume": [1] * 6}]}}]}}
    with pytest.raises(YahooDataError, match="not daily"):
        parse_chart(monthly, "X")


def test_period_bounds():
    assert period_bounds("max", now=1000) == (0, 1000)
    assert period_bounds("1y", now=10_000_000) == (10_000_000 - 366 * 86400, 10_000_000)
    with pytest.raises(ValueError):
        period_bounds("7w", now=0)
