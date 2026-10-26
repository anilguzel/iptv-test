"""Job definitions (from automation/jobs.json) and their runners."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..config import get_settings
from ..research.universe import resolve_universe
from .store import csv_path, merge_bars, read_store, write_store


@dataclass
class CollectJob:
    source: str                  # "stooq", "yahoo" or "bist"
    universe: str                # named universe or comma list
    benchmark: str | None = None
    dir: str | None = None       # store sub-folder (default: daily/<source>)
    suffix: str = ""             # yahoo: exchange suffix, e.g. ".IS" for Borsa Istanbul
    enabled: bool = True

    @property
    def store_dir(self) -> str:
        return self.dir or f"daily/{self.source}"


@dataclass
class ResearchJob:
    name: str
    dir: str                     # store sub-folder holding the CSVs
    mode: str = "cross_section"  # or "timeseries"
    universe: str | None = None
    symbol: str | None = None
    benchmark: str | None = None
    cost_bps: float = 10.0
    years: float = 3.0
    top_n: int = 5
    enabled: bool = True


@dataclass
class Config:
    collect: list[CollectJob] = field(default_factory=list)
    research: list[ResearchJob] = field(default_factory=list)


def load_config(path: str | Path) -> Config:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return Config(
        collect=[CollectJob(**{k: v for k, v in j.items() if not k.startswith("_")}) for j in raw.get("collect", [])],
        research=[ResearchJob(**{k: v for k, v in j.items() if not k.startswith("_")}) for j in raw.get("research", [])],
    )


def make_provider(source: str, suffix: str = ""):
    if source == "yahoo":
        from ..providers.yahoo import YahooChartProvider

        return YahooChartProvider(get_settings(), suffix=suffix)
    if source == "stooq":
        from ..providers.stooq import StooqProvider

        return StooqProvider(get_settings())
    if source == "bist":
        from ..providers.bist_data_service import BistDataServiceProvider

        return BistDataServiceProvider(get_settings())
    raise ValueError(f"unknown collect source {source!r}")


async def run_collect(job: CollectJob, store: Path, provider=None) -> dict:
    """Download each symbol's daily history and merge it into the store."""
    symbols = resolve_universe(job.universe)
    if job.benchmark and job.benchmark.upper() not in symbols:
        symbols.append(job.benchmark.upper())
    target = store / job.store_dir
    own_provider = provider is None
    provider = provider or make_provider(job.source, job.suffix)
    summary: dict = {"source": job.source, "universe": job.universe, "dir": job.store_dir,
                     "symbols": len(symbols), "changed": [], "unchanged": [], "failed": [],
                     "rescaled": [], "latest": {}}
    try:
        for sym in symbols:
            try:
                fresh = await provider.get_history(sym, interval="1d", period="max")
            except Exception as exc:  # report per symbol, keep going
                summary["failed"].append({"symbol": sym, "reason": f"{type(exc).__name__}: {exc}"[:200]})
                continue
            path = csv_path(target, sym)
            result = merge_bars(read_store(path, sym), fresh)
            if result.rescale_factor is not None:
                summary["rescaled"].append({"symbol": sym, "factor": round(result.rescale_factor, 6)})
            if result.added or result.updated or result.rescale_factor is not None or not path.exists():
                write_store(path, result.bars)
                summary["changed"].append(sym)
            else:
                summary["unchanged"].append(sym)
            if result.bars:
                summary["latest"][sym] = result.bars[-1].timestamp.date().isoformat()
    finally:
        if own_provider:
            await provider.aclose()
    return summary


def run_research(job: ResearchJob, store: Path, reports_dir: Path) -> dict:
    """Run one research job on stored CSVs; returns the written report (or an error dict)."""
    from ..research.__main__ import main as research_main

    get_settings().research_reports_dir = str(reports_dir)
    args = ["--source", "csv", "--csv-dir", str(store / job.dir), "--mode", job.mode, "--name", job.name,
            "--cost-bps", str(job.cost_bps), "--years", str(job.years), "--top-n", str(job.top_n)]
    if job.universe:
        args += ["--universe", job.universe]
    if job.symbol:
        args += ["--symbol", job.symbol]
    if job.benchmark:
        args += ["--benchmark", job.benchmark]
    try:
        code = research_main(args)
    except SystemExit as exc:  # argparse / guard exits
        code = exc.code if isinstance(exc.code, int) else 2
    path = reports_dir / f"{job.name}.json"
    if code != 0 or not path.exists():
        return {"name": job.name, "error": f"research exited with code {code}",
                "generated_at": datetime.now(UTC).isoformat()}
    return json.loads(path.read_text(encoding="utf-8"))
