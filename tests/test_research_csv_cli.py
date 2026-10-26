from __future__ import annotations

import json
from pathlib import Path

import pytest
from bist_core.config import get_settings
from bist_core.research.__main__ import main
from bist_core.research.synthetic import synthetic_single, synthetic_universe
from bist_core.schemas import OhlcvBar


def _write_csv(path: Path, bars: list[OhlcvBar]) -> None:
    lines = ["Date,Open,High,Low,Close,Volume"]
    lines += [f"{b.timestamp.date()},{b.open},{b.high},{b.low},{b.close},{b.volume}" for b in bars]
    path.write_text("\n".join(lines) + "\n")


@pytest.fixture
def reports(tmp_path, monkeypatch):
    out = tmp_path / "reports"
    monkeypatch.setattr(get_settings(), "research_reports_dir", str(out))
    return out


def test_csv_timeseries_end_to_end(tmp_path, reports):
    daily, bench = synthetic_single(n_weeks=160, autocorr=0.3, seed=2)
    data = tmp_path / "data"
    data.mkdir()
    _write_csv(data / "SMTK.csv", daily["SYNTS"])
    _write_csv(data / "IWM.csv", bench)

    code = main(["--source", "csv", "--csv-dir", str(data), "--mode", "timeseries", "--symbol", "SMTK",
                 "--years", "10", "--name", "smtk_ts"])
    assert code == 0
    report = json.loads((reports / "smtk_ts.json").read_text())
    assert report["mode"] == "timeseries"
    assert report["meta"]["source"] == "csv" and report["meta"]["benchmark_used"] == "IWM"
    assert report["next_week"]["symbol"] == "SMTK"


def test_csv_ranking_uses_every_file_except_benchmark(tmp_path, reports):
    daily, bench = synthetic_universe(n_stocks=12, n_weeks=140, momentum=0.5, seed=4)
    data = tmp_path / "data"
    data.mkdir()
    for sym, bars in daily.items():
        _write_csv(data / f"{sym}.csv", bars)
    _write_csv(data / "IWM.csv", bench)

    code = main(["--source", "csv", "--csv-dir", str(data), "--years", "10", "--top-n", "3",
                 "--min-train-weeks", "40", "--holdout-weeks", "10", "--name", "peers"])
    assert code == 0
    report = json.loads((reports / "peers.json").read_text())
    assert report["mode"] == "cross_section"
    assert "IWM" not in report["meta"]["symbols_used"] and len(report["meta"]["symbols_used"]) == 12


def test_csv_missing_symbol_reports_cleanly(tmp_path, reports, capsys):
    data = tmp_path / "empty"
    data.mkdir()
    code = main(["--source", "csv", "--csv-dir", str(data), "--mode", "timeseries", "--symbol", "SMTK"])
    assert code == 2
    assert "SMTK" in capsys.readouterr().err


def test_csv_timeseries_without_any_symbol_exits_cleanly(tmp_path, reports):
    data = tmp_path / "empty2"
    data.mkdir()
    with pytest.raises(SystemExit, match="no symbol"):
        main(["--source", "csv", "--csv-dir", str(data), "--mode", "timeseries"])
