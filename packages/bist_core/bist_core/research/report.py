"""Run the full research pipeline and build a JSON-serialisable report."""
from __future__ import annotations

from datetime import UTC, datetime

from ..schemas import OhlcvBar
from .features import FEATURE_NAMES, build_panel
from .models import RidgeRanker, default_strategies
from .walkforward import (
    WalkForwardConfig,
    eval_weeks,
    predict_next_week,
    run_strategy,
    verdict,
)
from .weekly import to_weekly

MIN_WEEKLY_BARS = 30  # symbols with less history than this are skipped

TACTIC_TR = (
    "Her hafta kapanışında model geçmiş haftalarla yeniden eğitilir; en yüksek skorlu "
    "{n} hisse eşit ağırlıkla 1 hafta tutulur. Başarı ölçüsü: kıyasa ({bench}) göre "
    "maliyet sonrası fazla getiri. Bu bir analizdir, otomatik emir değildir."
)


def run_research(
    daily_by_symbol: dict[str, list[OhlcvBar]],
    benchmark_daily: list[OhlcvBar] | None,
    cfg: WalkForwardConfig,
    *,
    ridge_lambda: float = 10.0,
    seed: int = 7,
    meta: dict | None = None,
) -> dict:
    weekly = {s: to_weekly(bars) for s, bars in daily_by_symbol.items()}
    skipped = sorted(s for s, w in weekly.items() if len(w) < MIN_WEEKLY_BARS)
    weekly = {s: w for s, w in weekly.items() if len(w) >= MIN_WEEKLY_BARS}
    bench_weekly = to_weekly(benchmark_daily) if benchmark_daily else None

    panel = build_panel(weekly, bench_weekly)
    weeks = eval_weeks(panel, cfg)

    results = {st.name: run_strategy(panel, st, weeks, cfg) for st in default_strategies(ridge_lambda, seed)}

    final_model = RidgeRanker(lam=ridge_lambda)
    next_week = predict_next_week(panel, final_model, cfg.top_n)
    next_week["coefficients"] = final_model.coefficients()
    next_week["note"] = "Analitik sıralama — otomatik emir değildir, gelecek garantisi yoktur."

    strategies = {}
    for name, res in results.items():
        equity, cum = [], 1.0
        for s in res.steps:
            cum *= 1 + s.net
            equity.append({"week_end": s.hold_week_end, "cum_net": round(cum - 1, 6)})
        strategies[name] = {
            "metrics": res.metrics,
            "equity": equity,
            "steps": [
                {
                    "signal_week_end": s.signal_week_end,
                    "hold_week_end": s.hold_week_end,
                    "train_max_week": s.train_max_week,
                    "week": s.week,
                    "top": s.top,
                    "net": round(s.net, 6),
                    "ic": None if s.ic is None else round(s.ic, 4),
                }
                for s in res.steps
            ],
        }

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "meta": {
            **(meta or {}),
            "benchmark_used": panel.benchmark,
            "symbols_used": sorted(weekly),
            "symbols_skipped_short_history": skipped,
            "calendar_weeks": len(panel.calendar),
            "first_week_end": panel.week_end[0] if panel.week_end else None,
            "last_week_end": panel.week_end[-1] if panel.week_end else None,
            "rows": len(panel.week),
            "evaluated_weeks": len(weeks),
            "segment": cfg.segment,
            "holdout_locked": cfg.segment != "holdout",
            "config": {
                "top_n": cfg.top_n,
                "min_train_weeks": cfg.min_train_weeks,
                "holdout_weeks": cfg.holdout_weeks,
                "cost_bps_per_side": cfg.cost_bps_per_side,
                "ridge_lambda": ridge_lambda,
            },
            "feature_names": list(FEATURE_NAMES),
        },
        "tactic_tr": TACTIC_TR.format(n=cfg.top_n, bench=panel.benchmark),
        "verdict": verdict(results),
        "strategies": strategies,
        "next_week": next_week,
    }
