"""CLI: weekly walk-forward research.

Examples::

    # Validate the harness on synthetic data with a planted signal / pure noise
    python -m bist_core.research --source synthetic --synthetic-momentum 0.5
    python -m bist_core.research --source synthetic --synthetic-momentum 0

    # Real run: 3 years of BIST30 daily bars from a running bist-data-service
    python -m bist_core.research --source bist --universe BIST30 --years 3

    # Only after you have finished tuning: open the locked holdout ONCE
    python -m bist_core.research --source bist --segment holdout --unlock-holdout

Run it after the Friday close so the latest weekly bar is complete.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from ..config import get_settings
from .data import load_daily
from .report import run_research
from .synthetic import synthetic_universe
from .universe import resolve_universe
from .walkforward import HoldoutLockedError, WalkForwardConfig


def _parse(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m bist_core.research", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", choices=["synthetic", "bist"], required=True,
                   help="synthetic: known-answer data; bist: the configured bist-data-service")
    p.add_argument("--universe", default="BIST30", help='"BIST30" or a comma-separated symbol list')
    p.add_argument("--benchmark", default="XU100", help="benchmark symbol; falls back to the universe average")
    p.add_argument("--years", type=float, default=3.0)
    p.add_argument("--top-n", type=int, default=5)
    p.add_argument("--min-train-weeks", type=int, default=52)
    p.add_argument("--holdout-weeks", type=int, default=26)
    p.add_argument("--cost-bps", type=float, default=10.0, help="trading cost per side, basis points")
    p.add_argument("--ridge-lambda", type=float, default=10.0)
    p.add_argument("--segment", choices=["validation", "holdout"], default="validation")
    p.add_argument("--unlock-holdout", action="store_true")
    p.add_argument("--synthetic-momentum", type=float, default=0.5)
    p.add_argument("--synthetic-stocks", type=int, default=30)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out", default=None, help="report path (default: RESEARCH_REPORT_PATH)")
    return p.parse_args(argv)


async def _load(args: argparse.Namespace) -> tuple[dict, list | None, dict]:
    if args.source == "synthetic":
        daily, bench = synthetic_universe(
            n_stocks=args.synthetic_stocks,
            n_weeks=int(args.years * 52) + 4,
            momentum=args.synthetic_momentum,
            seed=args.seed,
        )
        return daily, bench, {"source": "synthetic", "synthetic_momentum": args.synthetic_momentum,
                              "data_warning": "SYNTHETIC DATA — validates the method only, not a market result."}

    from ..providers.bist_data_service import BistDataServiceProvider

    symbols = resolve_universe(args.universe)
    provider = BistDataServiceProvider(get_settings())
    try:
        loaded = await load_daily(provider, symbols, years=args.years, benchmark=args.benchmark)
    finally:
        await provider.aclose()
    return loaded.daily_by_symbol, loaded.benchmark_daily, {
        "source": "bist-data-service",
        "universe": args.universe,
        "requested_symbols": symbols,
        "missing": loaded.missing,
        "data_warning": "Delayed public data; universe uses today's members (survivorship bias).",
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    daily, bench, meta = asyncio.run(_load(args))
    if not daily:
        print("No data loaded. Is bist-data-service running and BIST_DATA_SERVICE_URL set?", file=sys.stderr)
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
    try:
        report = run_research(daily, bench, cfg, ridge_lambda=args.ridge_lambda, seed=args.seed,
                              meta={**meta, "years": args.years})
    except (ValueError, HoldoutLockedError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out = Path(args.out or get_settings().research_report_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    print(f"source={report['meta']['source']} benchmark={report['meta']['benchmark_used']} "
          f"symbols={len(report['meta']['symbols_used'])} weeks={report['meta']['evaluated_weeks']} "
          f"segment={report['meta']['segment']}")
    print(f"{'strategy':<14}{'mean/wk':>10}{'hit':>7}{'sharpe':>8}{'cum':>9}{'maxDD':>9}{'IC':>8}{'IC t':>7}{'cons13':>8}")
    for name, s in report["strategies"].items():
        m = s["metrics"]

        def fmt(v, pct=False):
            if v is None:
                return "-"
            return f"{v * 100:.2f}%" if pct else f"{v:.2f}"

        print(f"{name:<14}{fmt(m['mean_weekly_net'], True):>10}{fmt(m['hit_rate'], True):>7}"
              f"{fmt(m['sharpe_annualised']):>8}{fmt(m['cumulative_net'], True):>9}{fmt(m['max_drawdown'], True):>9}"
              f"{fmt(m['mean_ic']):>8}{fmt(m['ic_tstat']):>7}{fmt(m['consistency_13w']):>8}")
    for name, v in report["verdict"]["models"].items():
        print(f"verdict[{name}]: {'PASS' if v['passed'] else 'FAIL'} — {v['summary_tr']}")
    picks = ", ".join(p["symbol"] for p in report["next_week"]["picks"])
    print(f"next week ({report['next_week']['as_of_week_end']}): {picks}")
    print(f"report -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
