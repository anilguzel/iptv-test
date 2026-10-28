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
    assert {j.name for j in cfg.research if j.enabled} >= {"smtk_peers", "smtk_timeseries", "bist_likit"}


# -- status page ------------------------------------------------------------------ #
def test_status_page_shows_data_and_research(tmp_path, monkeypatch):
    from bist_core.automation.status import write_status

    _store_synthetic(tmp_path, single=True)
    run_research(ResearchJob(name="smtk_ts", dir="daily/stooq", mode="timeseries", symbol="SMTK",
                             benchmark="IWM", cost_bps=75, years=10), tmp_path, tmp_path / "reports")
    summary = tmp_path / "step_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    text = write_status(tmp_path, event="Haftalık araştırma", extra="özet")

    readme = (tmp_path / "README.md").read_text()
    assert readme == text and "Haftalık araştırma" in readme
    assert "| stooq | 2 |" in readme  # SMTK + IWM stored
    assert "| smtk_ts | tek hisse |" in readme and "sinyal değil" in readme
    assert "özet" in summary.read_text()


def test_status_page_when_empty(tmp_path):
    from bist_core.automation.status import render_status

    text = render_status(tmp_path, event="Günlük veri toplama")
    assert "Henüz veri yok" in text and "Henüz rapor yok" in text


def test_collect_cli_writes_status(tmp_path, monkeypatch):
    from bist_core.automation import jobs as jobs_mod

    data = {"AAA": [_bar(D[0], 1, sym="AAA"), _bar(D[1], 2, sym="AAA")], "IWM": [_bar(D[0], 100, sym="IWM")]}
    monkeypatch.setattr(jobs_mod, "make_provider", lambda source, suffix="": FakeProvider(data))
    cfg = tmp_path / "jobs.json"
    cfg.write_text(json.dumps({"collect": [{"source": "yahoo", "universe": "AAA", "benchmark": "IWM"}]}))
    store = tmp_path / "store"
    assert automation_main(["collect", "--config", str(cfg), "--store", str(store)]) == 0
    readme = (store / "README.md").read_text()
    assert "Günlük veri toplama" in readme and "| yahoo | 2 |" in readme


def test_status_names_the_laggard_only_when_behind(tmp_path):
    from bist_core.automation.status import data_table

    write_store(csv_path(tmp_path / "daily/y", "AAA"), [_bar(D[0], 1), _bar(D[2], 1)])
    write_store(csv_path(tmp_path / "daily/y", "BBB"), [_bar(D[0], 1), _bar(D[2], 1)])
    assert "hepsi güncel" in "\n".join(data_table(tmp_path))
    write_store(csv_path(tmp_path / "daily/y", "CCC"), [_bar(D[0], 1)])
    assert f"CCC ({D[0].isoformat()})" in "\n".join(data_table(tmp_path))


# -- screening: long history + real volume ------------------------------------------ #
def _series(start: date, days: int, close: float, volume: float, sym: str) -> list[OhlcvBar]:
    return [_bar(start + timedelta(days=i), close, volume, sym) for i in range(days)]


def test_screen_keeps_long_liquid_stocks_and_says_why_others_drop(tmp_path):
    from bist_core.automation.screen import ScreenRules, screen_symbols

    old = date(2016, 1, 1)
    end_days = (date(2026, 1, 1) - old).days
    write_store(csv_path(tmp_path, "BIG"), _series(old, end_days, 10, 1_000_000, "BIG"))
    write_store(csv_path(tmp_path, "THIN"), _series(old, end_days, 10, 100, "THIN"))
    write_store(csv_path(tmp_path, "NEW"), _series(date(2024, 1, 1), 730, 10, 1_000_000, "NEW"))
    zero = _series(old, end_days, 10, 1_000_000, "ZERO")
    zero[-100:] = [b.model_copy(update={"volume": 0.0}) for b in zero[-100:]]
    write_store(csv_path(tmp_path, "ZERO"), zero)
    write_store(csv_path(tmp_path, "DEAD"), _series(old, end_days - 60, 10, 1_000_000, "DEAD"))

    rules = ScreenRules(min_years=8, min_median_value=1_000_000, max_zero_volume_share=0.05, max_stale_days=5)
    out = screen_symbols(tmp_path, ["BIG", "THIN", "NEW", "ZERO", "DEAD", "GONE"], rules)
    assert out["kept"] == ["BIG"]
    why = {r["symbol"]: " ".join(r["reasons"]) for r in out["rows"]}
    assert "işlem hacmi" in why["THIN"] and "geçmiş" in why["NEW"] and "hacimsiz" in why["ZERO"]
    assert "geride" in why["DEAD"] and why["GONE"] == "veri yok"
    assert not ScreenRules().active and rules.active


def test_research_job_runs_on_the_screened_universe(tmp_path):
    _store_synthetic(tmp_path)  # 12 synthetic stocks, ~2.7 years
    job = ResearchJob(name="screened", dir="daily/stooq", universe="",
                      benchmark="IWM", years=10, top_n=3, min_years=1)
    folder = tmp_path / "daily/stooq"
    names = sorted(p.stem for p in folder.glob("*.csv") if p.stem != "IWM")
    job.universe = ",".join([*names, "MISSING"])
    report = run_research(job, tmp_path, tmp_path / "reports")
    assert "MISSING" not in report["screen"]["kept"] and set(report["meta"]["symbols_used"]) <= set(names)
    assert "Eleme:" in summarize_report(report) and "MISSING (veri yok)" in summarize_report(report)
    saved = json.loads((tmp_path / "reports/screened.json").read_text())
    assert saved["screen"]["kept"] == report["screen"]["kept"]

    job.min_years = 50
    failed = run_research(job, tmp_path, tmp_path / "reports")
    assert "error" in failed and "Eleme: 0/" in summarize_report(failed)


def test_outlook_job_writes_report_csvs_and_summary(tmp_path):
    from bist_core.automation.status import render_status

    daily, _ = synthetic_universe(n_stocks=12, n_weeks=160, momentum=0.5, seed=4)
    for sym, bars in daily.items():
        write_store(csv_path(tmp_path / "daily/x", sym), bars)
    job = ResearchJob(name="gorunum", dir="daily/x", mode="outlook", top_n=3)
    report = run_research(job, tmp_path, tmp_path / "reports")
    assert report["mode"] == "outlook" and report["risk"]["stocks"]
    assert (tmp_path / "reports/gorunum_risk.csv").read_text().count("\n") == 13
    assert (tmp_path / "reports/gorunum_siralama.csv").exists()
    text = summarize_report(report)
    assert "sert oynayabilecekler" in text and "emir değildir" in text
    assert "gelecek hafta risk" in render_status(tmp_path, event="x")
