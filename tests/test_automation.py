from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime, timedelta

import pytest
from bist_core.automation.__main__ import main as automation_main
from bist_core.automation.jobs import CollectJob, ResearchJob, load_config, run_collect, run_research
from bist_core.automation.notify import summarize_collect, summarize_report
from bist_core.automation.store import csv_path, merge_bars, read_store, write_store
from bist_core.research.synthetic import synthetic_single, synthetic_universe
from bist_core.schemas import OhlcvBar


def _bar(day: date, close: float, volume: float = 100.0, sym: str = "X") -> OhlcvBar:
    return OhlcvBar(symbol=sym, timestamp=datetime(day.year, day.month, day.day, tzinfo=UTC),
                    open=close, high=close, low=close, close=close, volume=volume)


D = [date(2026, 1, 5) + timedelta(days=i) for i in range(6)]


# -- store / merge -------------------------------------------------------------- #
def test_merge_appends_new_days_and_new_values_win():
    old = [_bar(D[0], 10), _bar(D[1], 11)]
    new = [_bar(D[1], 11.0), _bar(D[2], 12)]
    r = merge_bars(old, new)
    assert [b.close for b in r.bars] == [10, 11, 12]
    assert (r.added, r.updated, r.rescale_factor) == (1, 0, None)


def test_merge_rescales_older_rows_after_a_reverse_split():
    # Stored history before a 1:10 reverse split; the source now reports all
    # prices x10. Overlap reveals the factor, older rows are rescaled.
    old = [_bar(D[0], 1.0, 1000), _bar(D[1], 1.1, 1000), _bar(D[2], 1.2, 1000)]
    new = [_bar(D[1], 11.0, 100), _bar(D[2], 12.0, 100), _bar(D[3], 13.0, 100)]
    r = merge_bars(old, new)
    assert r.rescale_factor == pytest.approx(10.0)
    assert [round(b.close, 6) for b in r.bars] == [10.0, 11.0, 12.0, 13.0]
    assert r.bars[0].volume == pytest.approx(100.0)  # volume scaled inversely


def test_store_roundtrip(tmp_path):
    bars = [_bar(D[0], 1.2345), _bar(D[1], 2.5, 12345)]
    path = csv_path(tmp_path, "abc")
    write_store(path, bars)
    back = read_store(path, "ABC")
    assert path.name == "ABC.csv"
    assert [b.close for b in back] == [1.2345, 2.5] and back[1].volume == 12345


# -- collect ---------------------------------------------------------------------- #
class FakeProvider:
    name = "fake"

    def __init__(self, data: dict[str, list[OhlcvBar]], fail: set[str] = frozenset()):
        self.data, self.fail = data, fail
        self.periods: dict[str, str] = {}

    async def get_history(self, symbol, *, interval="1d", limit=120, period=None):
        self.periods[symbol] = period
        if symbol in self.fail:
            raise RuntimeError("boom")
        return self.data[symbol]

    async def aclose(self):
        return None


def test_collect_writes_store_and_reports_failures(tmp_path):
    data = {"AAA": [_bar(D[0], 1, sym="AAA"), _bar(D[1], 2, sym="AAA")], "IWM": [_bar(D[0], 100, sym="IWM")]}
    job = CollectJob(source="stooq", universe="AAA,BBB", benchmark="IWM")
    summary = asyncio.run(run_collect(job, tmp_path, provider=FakeProvider(data, fail={"BBB"})))
    assert sorted(summary["changed"]) == ["AAA", "IWM"]
    assert [f["symbol"] for f in summary["failed"]] == ["BBB"]
    assert (tmp_path / "daily/stooq/AAA.csv").exists()

    # Second run with nothing new: no rewrite, and only the short update window is requested.
    second = FakeProvider(data, fail={"BBB"})
    again = asyncio.run(run_collect(job, tmp_path, provider=second))
    assert again["changed"] == [] and sorted(again["unchanged"]) == ["AAA", "IWM"]
    assert second.periods == {"AAA": "1y", "BBB": "10y", "IWM": "1y"}  # BBB was never stored -> backfill


def test_collect_warning_text():
    summary = {"dir": "daily/stooq", "symbols": 3, "failed": [{"symbol": "BBB", "reason": "x"}],
               "rescaled": [{"symbol": "AAA", "factor": 10.0}], "latest": {"AAA": "2026-01-02", "IWM": "2026-01-09"}}
    text = summarize_collect([summary], today=date(2026, 1, 9))
    assert "BBB" in text and "AAA" in text and "split" in text
    clean = {"dir": "d", "symbols": 1, "failed": [], "rescaled": [], "latest": {"IWM": "2026-01-09"}}
    assert summarize_collect([clean], today=date(2026, 1, 9)) is None


# -- research on the store + Telegram text ------------------------------------------ #
def _store_synthetic(store, *, single=False):
    target = store / "daily/stooq"
    if single:
        daily, bench = synthetic_single(n_weeks=160, autocorr=0.0, seed=1)
        daily = {"SMTK": daily["SYNTS"]}
    else:
        daily, bench = synthetic_universe(n_stocks=12, n_weeks=140, momentum=0.5, seed=4)
    for sym, bars in daily.items():
        write_store(csv_path(target, sym), bars)
    write_store(csv_path(target, "IWM"), bench)


def test_research_job_on_store_and_fail_summary_says_not_a_signal(tmp_path):
    _store_synthetic(tmp_path, single=True)
    job = ResearchJob(name="smtk_ts", dir="daily/stooq", mode="timeseries", symbol="SMTK",
                      benchmark="IWM", cost_bps=75, years=10)
    report = run_research(job, tmp_path, tmp_path / "reports")
    assert report["mode"] == "timeseries" and report["name"] == "smtk_ts"
    text = summarize_report(report)
    assert "FAIL" in text and "sinyal sayılmaz" in text and "emir değildir" in text


def test_research_job_error_is_reported(tmp_path):
    job = ResearchJob(name="nothing", dir="daily/missing", mode="timeseries", symbol="SMTK", years=10)
    report = run_research(job, tmp_path, tmp_path / "reports")
    assert "error" in report
    assert "çalışmadı" in summarize_report(report)


def test_cli_research_runs_enabled_jobs_only(tmp_path, capsys):
    _store_synthetic(tmp_path)
    cfg = tmp_path / "jobs.json"
    cfg.write_text(json.dumps({"research": [
        {"name": "peers", "dir": "daily/stooq", "benchmark": "IWM", "years": 10, "top_n": 3, "cost_bps": 10},
        {"name": "off", "dir": "daily/stooq", "enabled": False},
    ]}))
    assert automation_main(["research", "--config", str(cfg), "--store", str(tmp_path)]) == 0
    assert (tmp_path / "reports/peers.json").exists()
    assert not (tmp_path / "reports/off.json").exists()
    assert "peers" in capsys.readouterr().out


def test_repository_job_config_parses():
    cfg = load_config("automation/jobs.json")
    assert any(j.enabled and j.source == "yahoo" and j.suffix == ".IS" for j in cfg.collect)  # BIST on
    assert {j.name for j in cfg.research if j.enabled} >= {"smtk_peers", "smtk_timeseries", "bist30"}
