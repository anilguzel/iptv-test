from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from bist_core.research.report import run_research
from bist_core.research.synthetic import synthetic_universe
from bist_core.research.walkforward import WalkForwardConfig
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))
from app import main

CFG = WalkForwardConfig(top_n=4, min_train_weeks=40, holdout_weeks=10)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main.settings, "research_reports_dir", str(tmp_path))
    return TestClient(main.app)  # no `with`: startup (DB init) is not needed here


def _write(tmp_path: Path, name: str, generated_at: str) -> None:
    daily, bench = synthetic_universe(n_stocks=12, n_weeks=120, momentum=0.5, seed=1)
    report = run_research(daily, bench, CFG)
    report["generated_at"] = generated_at
    (tmp_path / f"{name}.json").write_text(json.dumps(report))


def test_no_reports_yet(client):
    assert client.get("/research/reports").json() == []
    body = client.get("/research").json()
    assert body["available"] is False and "bist_core.research" in body["how_to_run"]


def test_lists_and_serves_reports(client, tmp_path):
    _write(tmp_path, "older", "2026-01-01T00:00:00+00:00")
    _write(tmp_path, "newer", "2026-02-01T00:00:00+00:00")

    listed = client.get("/research/reports").json()
    assert [r["name"] for r in listed] == ["newer", "older"]
    assert listed[0]["mode"] == "cross_section"

    default = client.get("/research").json()
    assert default["name"] == "newer"
    assert all("steps" not in s for s in default["strategies"].values())

    full = client.get("/research", params={"name": "older", "full": "true"}).json()
    assert full["name"] == "older"
    assert all("steps" in s for s in full["strategies"].values())


def test_rejects_bad_or_unknown_names(client):
    assert client.get("/research", params={"name": "../etc/passwd"}).status_code == 400
    assert client.get("/research", params={"name": "nope"}).status_code == 404
