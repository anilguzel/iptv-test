"""Telegram texts for the scheduled jobs (plain text, Turkish)."""
from __future__ import annotations

from datetime import date

from ..config import Settings, get_settings
from ..notifications.telegram import TelegramNotifier

TELEGRAM_LIMIT = 4000  # Telegram caps messages at 4096 characters
STALE_DAYS = 5         # latest bar older than this (calendar days) => warn


def _pct(v) -> str:
    return "-" if v is None else f"{v * 100:+.2f}%"


def _num(v) -> str:
    return "-" if v is None else f"{v:.2f}"


def summarize_report(report: dict) -> str:
    if "error" in report:
        return f"⚠️ {report['name']}: araştırma çalışmadı ({report['error']})."
    m = report["meta"]
    ridge = report["strategies"]["ridge"]["metrics"]
    verdict = report["verdict"]["models"]["ridge"]
    passed = verdict["passed"]
    ts = report["mode"] == "timeseries"
    title = f"tek hisse {m.get('symbol')}" if ts else f"sıralama, {len(m['symbols_used'])} hisse"
    lines = [
        f"📊 {report.get('name', 'araştırma')} ({title}, kıyas {m['benchmark_used']})",
        f"Dönem: {m['first_week_end']} → {m['last_week_end']}, {m['evaluated_weeks']} hafta",
        f"Model: {'PASS ✅' if passed else 'FAIL ❌'} | IC {_num(ridge.get('mean_ic'))} (t {_num(ridge.get('ic_tstat'))})"
        f" | haftalık net {_pct(ridge.get('mean_weekly_net'))} | toplam {_pct(ridge.get('cumulative_net'))}",
    ]
    best = report["verdict"].get("best_baseline")
    if best:
        b = report["strategies"][best]["metrics"]
        lines.append(f"En iyi basit strateji: {best} {_pct(b.get('mean_weekly_net'))}/hafta, toplam {_pct(b.get('cumulative_net'))}")
    nw = report["next_week"]
    label = "Gelecek hafta" if passed else "Gelecek hafta (model FAIL — sinyal sayılmaz)"
    if ts:
        lines.append(f"{label}: {nw['symbol']} {nw['position']} (tahmin {_pct(nw['predicted_excess'])})")
    else:
        lines.append(f"{label}: " + ", ".join(p["symbol"] for p in nw["picks"]))
    if m.get("missing"):
        lines.append("Eksik veri: " + ", ".join(x["symbol"] for x in m["missing"][:10]))
    lines.append("Analizdir, otomatik emir değildir.")
    return "\n".join(lines)


def summarize_collect(summaries: list[dict], today: date | None = None) -> str | None:
    """A warning text when something needs attention, otherwise None."""
    today = today or date.today()
    problems: list[str] = []
    for s in summaries:
        if s["failed"]:
            names = ", ".join(f["symbol"] for f in s["failed"][:10])
            problems.append(f"{s['dir']}: {len(s['failed'])}/{s['symbols']} sembol çekilemedi ({names})")
        stale = [sym for sym, d in s["latest"].items() if (today - date.fromisoformat(d)).days > STALE_DAYS]
        if stale:
            problems.append(f"{s['dir']}: {STALE_DAYS} günden eski veri: {', '.join(stale[:10])}")
        for r in s["rescaled"]:
            problems.append(f"{s['dir']}: {r['symbol']} geçmişi yeniden düzeltildi (çarpan {r['factor']}), muhtemelen split")
    if not problems:
        return None
    return "⚠️ Günlük veri toplama uyarısı\n" + "\n".join(problems)


async def send(text: str, settings: Settings | None = None) -> bool:
    """Send to Telegram when configured; always print so the CI log has it too."""
    text = text[:TELEGRAM_LIMIT]
    print(text)
    notifier = TelegramNotifier(settings or get_settings())
    if not notifier.enabled:
        print("(Telegram not configured — message only logged)")
        return False
    return await notifier.send(text)
