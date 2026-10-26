"""A human-readable status page for the data branch.

Written to <store>/README.md after every collect/research run, so the branch's
front page on GitHub always shows what the automation has been doing, and
appended to the GitHub Actions step summary of the run.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

INTRO = """# market-data

Bu dal GitHub Actions tarafından otomatik yazılır; elle düzenlemeyin.

- `daily/<kaynak>/<SEMBOL>.csv`: günlük fiyatlar (her iş günü kapanıştan sonra eklenir)
- `reports/<isim>.json`: haftalık walk-forward araştırma raporları

Bu bir analizdir; buradaki hiçbir şey emir ya da yatırım tavsiyesi değildir.
"""


def _pct(v) -> str:
    return "-" if v is None else f"{v * 100:+.1f}%"


def data_table(store: Path) -> list[str]:
    rows = ["| Kaynak | Hisse | En güncel gün | En geride kalan |", "|---|---|---|---|"]
    for d in sorted(p for p in (store / "daily").glob("*") if p.is_dir()):
        last: dict[str, str] = {}
        for f in d.glob("*.csv"):
            lines = f.read_text(encoding="utf-8").strip().splitlines()
            if len(lines) > 1:
                last[f.stem] = lines[-1].split(",", 1)[0]
        if not last:
            continue
        laggard, newest = min(last, key=last.get), max(last.values())
        behind = "hepsi güncel" if last[laggard] == newest else f"{laggard} ({last[laggard]})"
        rows.append(f"| {d.name} | {len(last)} | {newest} | {behind} |")
    return rows if len(rows) > 2 else ["_Henüz veri yok._"]


def research_table(store: Path) -> list[str]:
    rows = ["| Rapor | Tür | Tarih | Sonuç | IC t | Toplam (model) | Gelecek hafta |", "|---|---|---|---|---|---|---|"]
    for f in sorted((store / "reports").glob("*.json")):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
            verdict = r["verdict"]["models"]["ridge"]
            m = r["strategies"]["ridge"]["metrics"]
            nw = r["next_week"]
        except (OSError, json.JSONDecodeError, KeyError):
            continue
        ts = r.get("mode") == "timeseries"
        nxt = f"{nw['symbol']} {nw['position']}" if ts else ", ".join(p["symbol"] for p in nw["picks"])
        if not verdict["passed"]:
            nxt += " _(model FAIL: sinyal değil)_"
        ic_t = m.get("ic_tstat")
        rows.append(
            f"| {f.stem} | {'tek hisse' if ts else 'sıralama'} | {(r.get('generated_at') or '')[:10]} "
            f"| {'PASS ✅' if verdict['passed'] else 'FAIL ❌'} | {'-' if ic_t is None else f'{ic_t:.2f}'} "
            f"| {_pct(m.get('cumulative_net'))} | {nxt} |"
        )
    return rows if len(rows) > 2 else ["_Henüz rapor yok (ilk araştırma Cumartesi çalışır)._"]


def render_status(store: Path, *, event: str, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return "\n".join([
        INTRO,
        "## Durum",
        f"Son çalışma: **{event}**, {now:%Y-%m-%d %H:%M} UTC",
        "",
        "### Veri",
        *data_table(store),
        "",
        "### Haftalık araştırma",
        *research_table(store),
        "",
    ])


def write_status(store: Path, *, event: str, extra: str | None = None) -> str:
    """Write <store>/README.md and append to the Actions step summary if present."""
    text = render_status(store, event=event)
    store.mkdir(parents=True, exist_ok=True)
    (store / "README.md").write_text(text, encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text)
            if extra:
                fh.write("\n```\n" + extra + "\n```\n")
    return text
