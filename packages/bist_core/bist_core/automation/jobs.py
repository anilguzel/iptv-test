"""Job definitions (from automation/jobs.json) and their runners."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..config import get_settings
from ..research.universe import resolve_universe
from .screen import ScreenRules, screen_symbols
from .store import csv_path, merge_bars, read_store, write_store


@dataclass
class CollectJob:
    source: str                  # "stooq", "yahoo", "evds" (TCMB series) or "bist"
    universe: str                # named universe or comma list
    benchmark: str | None = None
    dir: str | None = None       # store sub-folder (default: daily/<source>)
    suffix: str = ""             # yahoo: exchange suffix, e.g. ".IS" for Borsa Istanbul
    backfill_period: str = "10y"  # first download of a symbol
    update_period: str = "1y"     # later runs; the overlap also reveals re-adjustments
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
    # Screening (cross_section only): drop stocks with short history, thin
    # trading or broken volume data before the walk-forward. 0 / 1.0 = off.
    min_years: float = 0.0
    min_median_value: float = 0.0
    max_zero_volume_share: float = 1.0
    max_stale_days: int | None = None
    relative_to: str = "benchmark"  # or "universe": excess vs the stocks' own equal-weighted average
    fx: str | None = None        # store path of a USD/TRY CSV, e.g. "daily/evds/TP.DK.USD.A.csv"
    enabled: bool = True

    @property
    def screen_rules(self) -> ScreenRules:
        return ScreenRules(min_years=self.min_years, min_median_value=self.min_median_value,
                           max_zero_volume_share=self.max_zero_volume_share,
                           max_stale_days=self.max_stale_days)


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
    if source == "evds":
        from ..providers.evds import EvdsHistoryProvider

        return EvdsHistoryProvider(get_settings())
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
            path = csv_path(target, sym)
            period = job.update_period if path.exists() else job.backfill_period
            try:
                fresh = await provider.get_history(sym, interval="1d", period=period)
            except Exception as exc:  # report per symbol, keep going
                summary["failed"].append({"symbol": sym, "reason": f"{type(exc).__name__}: {exc}"[:200]})
                continue
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


def _run_outlook(job: ResearchJob, store: Path, reports_dir: Path, universe: str | None, screen: dict | None) -> dict:
    """Risk forecast and 3/6-month ranking (research/outlook.py) on stored CSVs."""
    from ..research.outlook import run_outlook

    folder = store / job.dir
    symbols = resolve_universe(universe) if universe else sorted(p.stem for p in folder.glob("*.csv"))
    daily = {s: bars for s in symbols if (bars := read_store(csv_path(folder, s), s))}
    try:
        report = run_outlook(daily, top_n=job.top_n, cost_bps=job.cost_bps)
    except (ValueError, ZeroDivisionError) as exc:
        return {"name": job.name, "mode": "outlook", "error": str(exc), "generated_at": datetime.now(UTC).isoformat()}
    report["name"] = job.name
    if screen is not None:
        report["screen"] = screen
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / f"{job.name}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    risk = report["risk"].get("stocks", [])
    lines = ["risk_rank,symbol,close,expected_move_pct,range_low_pct,range_high_pct,price_low,price_high"]
    lines += [f"{r['risk_rank']},{r['symbol']},{r['close']},{r['expected_move'] * 100:.2f},{r['range_low'] * 100:.2f},"
              f"{r['range_high'] * 100:.2f},{r['price_low']},{r['price_high']}" for r in risk]
    (reports_dir / f"{job.name}_risk.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    ranking = report["medium_term"].get("ranking") or []
    rlines = ["rank,symbol,pick"] + [f"{r['rank']},{r['symbol']},{'EVET' if r['pick'] else ''}" for r in ranking]
    (reports_dir / f"{job.name}_siralama.csv").write_text("\n".join(rlines) + "\n", encoding="utf-8")
    odds = report.get("odds", {}).get("stocks", [])
    if odds:
        cols = [k for k in odds[0] if k != "symbol"]
        olines = [",".join(["symbol", *cols])] + [",".join([o["symbol"], *(str(o.get(c, "")) for c in cols)]) for o in odds]
        (reports_dir / f"{job.name}_olasilik.csv").write_text("\n".join(olines) + "\n", encoding="utf-8")
    return report


def run_research(job: ResearchJob, store: Path, reports_dir: Path) -> dict:
    """Run one research job on stored CSVs; returns the written report (or an error dict)."""
    from ..research.__main__ import main as research_main

    get_settings().research_reports_dir = str(reports_dir)
    universe, screen = job.universe, None
    if job.mode in ("cross_section", "outlook") and job.universe and job.screen_rules.active:
        candidates = [s for s in resolve_universe(job.universe) if s != (job.benchmark or "").upper()]
        screen = screen_symbols(store / job.dir, candidates, job.screen_rules)
        if not screen["kept"]:
            return {"name": job.name, "error": "eleme filtresini geçen hisse yok", "screen": screen,
                    "generated_at": datetime.now(UTC).isoformat()}
        universe = ",".join(screen["kept"])
    if job.mode == "outlook":
        return _run_outlook(job, store, reports_dir, universe, screen)
    args = ["--source", "csv", "--csv-dir", str(store / job.dir), "--mode", job.mode, "--name", job.name,
            "--cost-bps", str(job.cost_bps), "--years", str(job.years), "--top-n", str(job.top_n)]
    if universe:
        args += ["--universe", universe]
    if job.symbol:
        args += ["--symbol", job.symbol]
    if job.benchmark:
        args += ["--benchmark", job.benchmark]
    if job.relative_to == "universe":
        args += ["--relative-to", "universe"]
    if job.fx and job.mode == "cross_section":
        args += ["--fx-csv", str(store / job.fx)]
    try:
        code = research_main(args)
    except SystemExit as exc:  # argparse / guard exits
        code = exc.code if isinstance(exc.code, int) else 2
    path = reports_dir / f"{job.name}.json"
    if code != 0 or not path.exists():
        return {"name": job.name, "error": f"research exited with code {code}",
                "generated_at": datetime.now(UTC).isoformat()}
    report = json.loads(path.read_text(encoding="utf-8"))
    if screen is not None:
        report["screen"] = screen
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if report.get("forecast"):
        from ..research.forecast import forecast_csv, history_csv

        (reports_dir / f"{job.name}_tahmin.csv").write_text(forecast_csv(report["forecast"]), encoding="utf-8")
        (reports_dir / f"{job.name}_gecmis.csv").write_text(history_csv(report["forecast"]), encoding="utf-8")
    return report
