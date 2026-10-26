"""CLI for the scheduled jobs.

    python -m bist_core.automation collect  --config automation/jobs.json --store store
    python -m bist_core.automation research --config automation/jobs.json --store store
    python -m bist_core.automation probe    --config automation/probe.json

probe:    tries each collect job in --config into a temporary folder and prints
          which sources/symbols work (GitHub step summary too). Exit 1 if none work.
collect:  downloads every enabled collect job into <store>/<dir>/<SYMBOL>.csv
          and alerts on Telegram if something failed, went stale or was re-adjusted.
          Exit code 1 if nothing at all could be downloaded.
research: runs every enabled research job on the stored CSVs, writes
          <store>/reports/<name>.json and sends one Telegram summary per job.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
from pathlib import Path

from .jobs import load_config, run_collect, run_research
from .notify import send, summarize_collect, summarize_report
from .status import write_status
from .store import csv_path, read_store


async def _collect(cfg, store: Path) -> int:
    summaries = [await run_collect(job, store) for job in cfg.collect if job.enabled]
    for s in summaries:
        print(json.dumps({k: s[k] for k in ("dir", "symbols", "changed", "failed", "rescaled")}, ensure_ascii=False))
    total = sum(s["symbols"] for s in summaries)
    failed = sum(len(s["failed"]) for s in summaries)
    warning = summarize_collect(summaries)
    if warning:
        await send(warning)
    write_status(store, event="Günlük veri toplama", extra=warning)
    return 1 if total and failed == total else 0


def _research(cfg, store: Path) -> int:
    # Synchronous on purpose: each research job runs its own asyncio.run() to
    # load data, which can't happen inside an already running event loop.
    reports_dir = store / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    texts, errors = [], 0
    for job in cfg.research:
        if not job.enabled:
            continue
        report = run_research(job, store, reports_dir)
        errors += "error" in report
        texts.append(summarize_report(report))

    async def _send_all() -> None:
        for text in texts:
            await send(text)

    asyncio.run(_send_all())
    write_status(store, event="Haftalık araştırma", extra="\n\n".join(texts) or None)
    return 1 if errors else 0


async def _probe(cfg) -> int:
    """Try every job (enabled or not) into a throwaway store and tabulate the outcome."""
    rows: list[tuple[str, str, str]] = []
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp)
        for job in cfg.collect:
            label = job.source + (f" ({job.suffix})" if job.suffix else "")
            try:
                summary = await run_collect(job, store)
            except Exception as exc:  # e.g. provider misconfigured
                rows.append((label, "*", f"FAILED: {type(exc).__name__}: {exc}"[:160]))
                continue
            failed = {f["symbol"]: f["reason"] for f in summary["failed"]}
            for sym in [*summary["changed"], *summary["unchanged"], *failed]:
                if sym in failed:
                    rows.append((label, sym, f"FAILED: {failed[sym]}"))
                    continue
                bars = read_store(csv_path(store / job.store_dir, sym), sym)
                rows.append((label, sym, f"ok: {len(bars)} bars, {bars[0].timestamp.date()} -> {bars[-1].timestamp.date()}"))

    table = ["| source | symbol | result |", "|---|---|---|"] + [f"| {a} | {b} | {c} |" for a, b, c in rows]
    print("\n".join(table))
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as fh:
            fh.write("## Data source probe\n\n" + "\n".join(table) + "\n")
    return 0 if any(r[2].startswith("ok") for r in rows) else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m bist_core.automation", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["collect", "research", "probe"])
    p.add_argument("--config", default="automation/jobs.json")
    p.add_argument("--store", default="store")
    args = p.parse_args(argv)
    cfg = load_config(args.config)
    store = Path(args.store)
    if args.command == "probe":
        return asyncio.run(_probe(cfg))
    if args.command == "collect":
        return asyncio.run(_collect(cfg, store))
    return _research(cfg, store)


if __name__ == "__main__":
    raise SystemExit(main())
