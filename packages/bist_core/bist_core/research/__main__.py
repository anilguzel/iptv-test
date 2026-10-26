"""CLI: weekly walk-forward research.

Modes:
  cross_section  rank a universe each week and hold the top N (default)
  timeseries     predict ONE stock's next week from its own history

Examples::

    # Validate the method on data with a known answer
    python -m bist_core.research --source synthetic --synthetic-momentum 0.5        # should PASS
    python -m bist_core.research --source synthetic --synthetic-momentum 0          # must FAIL
    python -m bist_core.research --source synthetic --mode timeseries --synthetic-autocorr 0.2

    # BIST30 from a running bist-data-service (run after the Friday close)
    python -m bist_core.research --source bist --universe BIST30 --years 3

    # SMTK on Nasdaq via Stooq: peer group, then the stock on its own
    python -m bist_core.research --source stooq --universe SMTK_PEERS --benchmark IWM \\
        --cost-bps 75 --name smtk_peers
    python -m bist_core.research --source stooq --mode timeseries --symbol SMTK --benchmark IWM \\
        --cost-bps 75 --name smtk_timeseries

    # Offline: a folder of CSVs (e.g. Yahoo "Historical Data -> Download"), SMTK.csv + IWM.csv
    python -m bist_core.research --source csv --csv-dir data --mode timeseries --symbol SMTK \\
        --benchmark IWM --cost-bps 75 --name smtk_timeseries

    # Only after you have finished tuning: open the locked holdout ONCE
    python -m bist_core.research --source bist --segment holdout --unlock-holdout

Reports go to RESEARCH_REPORTS_DIR/<name>.json and are listed at GET /research/reports.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from ..config import get_settings
from .data import detect_jumps, load_daily
from .report import run_research, run_timeseries_research
from .synthetic import synthetic_single, synthetic_universe
from .universe import resolve_universe
from .walkforward import HoldoutLockedError, WalkForwardConfig

DEFAULT_REPORT_NAME = "research_latest"


def _parse(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m bist_core.research", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", choices=["synthetic", "bist", "stooq", "csv"], required=True,
                   help="synthetic: known-answer data; bist: bist-data-service; stooq: Stooq (e.g. US stocks); "
                        "csv: a folder of <SYMBOL>.csv files (--csv-dir)")
    p.add_argument("--mode", choices=["cross_section", "timeseries"], default="cross_section")
    p.add_argument("--universe", default=None,
                   help='"BIST30", "SMTK_PEERS" or a comma-separated list (default: BIST30 for bist, SMTK_PEERS for '
                        'stooq, every file for csv)')
    p.add_argument("--csv-dir", default="data", help="csv source: folder of <SYMBOL>.csv files")
    p.add_argument("--symbol", default=None, help="timeseries mode: the stock (default: first in --universe)")
    p.add_argument("--benchmark", default=None,
                   help="benchmark symbol (default: XU100 for bist, IWM for stooq); falls back if unavailable")
    p.add_argument("--years", type=float, default=3.0)
    p.add_argument("--top-n", type=int, default=5)
    p.add_argument("--min-train-weeks", type=int, default=52)
    p.add_argument("--holdout-weeks", type=int, default=26)
    p.add_argument("--cost-bps", type=float, default=10.0, help="trading cost per side in basis points")
    p.add_argument("--ridge-lambda", type=float, default=10.0)
    p.add_argument("--segment", choices=["validation", "holdout"], default="validation")
    p.add_argument("--unlock-holdout", action="store_true")
    p.add_argument("--synthetic-momentum", type=float, default=0.5, help="cross_section synthetic effect")
    p.add_argument("--synthetic-autocorr", type=float, default=0.2, help="timeseries synthetic effect")
    p.add_argument("--synthetic-stocks", type=int, default=30)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--name", default=DEFAULT_REPORT_NAME, help="report name -> <RESEARCH_REPORTS_DIR>/<name>.json")
    args = p.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", args.name):
        p.error("--name may only contain letters, digits, '_' and '-'")
    return args


async def _load(args: argparse.Namespace) -> tuple[dict, list | None, str, dict]:
    """Returns (daily_by_symbol, benchmark_daily, benchmark_name, meta)."""
    if args.source == "synthetic":
        n_weeks = int(args.years * 52) + 4
        # Anchor the synthetic calendar so it ends with the last completed week (Monday start).
        today = date.today()
        start = today - timedelta(days=today.weekday() + 7 * n_weeks)
        if args.mode == "timeseries":
            daily, bench = synthetic_single(n_weeks=n_weeks, autocorr=args.synthetic_autocorr, seed=args.seed,
                                            start=start)
            effect = {"synthetic_autocorr": args.synthetic_autocorr}
        else:
            daily, bench = synthetic_universe(n_stocks=args.synthetic_stocks, n_weeks=n_weeks,
                                              momentum=args.synthetic_momentum, seed=args.seed, start=start)
            effect = {"synthetic_momentum": args.synthetic_momentum}
        return daily, bench, "BENCH" if args.mode == "timeseries" else "XU100", {
            "source": "synthetic", **effect,
            "data_warning": "SYNTHETIC DATA — validates the method only, not a market result.",
        }

    if args.source == "stooq":
        from ..providers.stooq import StooqProvider

        provider, benchmark = StooqProvider(get_settings()), args.benchmark or "IWM"
        default_universe = "SMTK_PEERS"
        warning = "Public end-of-day data (Stooq). Peer list is hand-picked and uses today's listings (survivorship bias)."
    elif args.source == "csv":
        from ..providers.csv_ohlcv import CsvDirProvider

        provider, benchmark = CsvDirProvider(args.csv_dir), args.benchmark or "IWM"
        default_universe = None  # every CSV in the folder except the benchmark
        warning = f"Local CSV files from {args.csv_dir}; check that prices are split-adjusted."
    else:
        from ..providers.bist_data_service import BistDataServiceProvider

        provider, benchmark = BistDataServiceProvider(get_settings()), args.benchmark or "XU100"
        default_universe = "BIST30"
        warning = "Delayed public data; universe uses today's members (survivorship bias)."

    universe = args.universe or default_universe
    if universe:
        symbols = resolve_universe(universe)
    else:
        symbols = [s for s in provider.symbols() if s != benchmark.upper()]
        universe = "csv:" + ",".join(symbols)
    if args.mode == "timeseries":
        if not (args.symbol or symbols):
            raise SystemExit("error: no symbol to analyse (pass --symbol or add CSV files)")
        symbols = [(args.symbol or symbols[0]).upper()]
    try:
        loaded = await load_daily(provider, symbols, years=args.years, benchmark=benchmark)
    finally:
        await provider.aclose()
    return loaded.daily_by_symbol, loaded.benchmark_daily, benchmark.upper(), {
        "source": provider.name,
        "universe": universe if args.mode == "cross_section" else symbols[0],
        "requested_symbols": symbols,
        "missing": loaded.missing,
        "jump_warnings": detect_jumps(loaded.daily_by_symbol),
        "data_warning": warning,
    }


def _fmt(v, pct: bool = False) -> str:
    if v is None:
        return "-"
    return f"{v * 100:.2f}%" if pct else f"{v:.2f}"


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    daily, bench, bench_name, meta = asyncio.run(_load(args))
    if not daily:
        print("No data loaded.", file=sys.stderr)
        for m in meta.get("missing", [])[:10]:
            print(f"  {m['symbol']}: {m['reason']}", file=sys.stderr)
        return 2

    cfg = WalkForwardConfig(
        top_n=args.top_n,
        min_train_weeks=args.min_train_weeks,
        holdout_weeks=args.holdout_weeks,
        cost_bps_per_side=args.cost_bps,
        segment=args.segment,
        unlock_holdout=args.unlock_holdout,
    )
    common = {"benchmark_name": bench_name, "ridge_lambda": args.ridge_lambda, "seed": args.seed,
              "meta": {**meta, "years": args.years}}
    try:
        if args.mode == "timeseries":
            (symbol, bars), = daily.items()
            report = run_timeseries_research(bars, symbol, bench, cfg, **common)
        else:
            report = run_research(daily, bench, cfg, **common)
    except (ValueError, HoldoutLockedError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report["name"] = args.name

    out = Path(get_settings().research_reports_dir) / f"{args.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    m = report["meta"]
    print(f"mode={report['mode']} source={m['source']} benchmark={m['benchmark_used']} "
          f"symbols={len(m['symbols_used'])} weeks={m['evaluated_weeks']} "
          f"({m['first_week_end']} -> {m['last_week_end']}) segment={m['segment']}")
    if m.get("missing"):
        print("missing: " + ", ".join(x["symbol"] for x in m["missing"]))
    if m.get("jump_warnings"):
        print("large one-day moves (check for unadjusted splits): "
              + ", ".join(f"{j['symbol']} {j['date']} {j['change'] * 100:+.0f}%" for j in m["jump_warnings"][:8]))
    print(f"{'strategy':<14}{'mean/wk':>10}{'hit':>8}{'sharpe':>8}{'cum':>10}{'maxDD':>9}{'IC':>8}{'IC t':>7}{'cons13':>8}")
    for name, s in report["strategies"].items():
        x = s["metrics"]
        print(f"{name:<14}{_fmt(x['mean_weekly_net'], True):>10}{_fmt(x['hit_rate'], True):>8}"
              f"{_fmt(x['sharpe_annualised']):>8}{_fmt(x['cumulative_net'], True):>10}{_fmt(x['max_drawdown'], True):>9}"
              f"{_fmt(x['mean_ic']):>8}{_fmt(x['ic_tstat']):>7}{_fmt(x['consistency_13w']):>8}")
    for name, v in report["verdict"]["models"].items():
        print(f"verdict[{name}]: {'PASS' if v['passed'] else 'FAIL'} — {v['summary_tr']}")
    nw = report["next_week"]
    if report["mode"] == "timeseries":
        print(f"next week ({nw['as_of_week_end']}): {nw['symbol']} {nw['position']} "
              f"(predicted excess {nw['predicted_excess'] * 100:+.2f}%)")
    else:
        print(f"next week ({nw['as_of_week_end']}): " + ", ".join(p["symbol"] for p in nw["picks"]))
    print(f"report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
