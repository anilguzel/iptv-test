"""Run the research pipelines and build JSON-serialisable reports."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from ..schemas import OhlcvBar
from .features import FEATURE_NAMES, Panel, build_panel
from .forecast import build_forecast
from .models import RidgeRanker, default_strategies
from .selection import select_strategy
from .timeseries import TSRidge, default_ts_strategies, predict_next_week_ts, run_ts_strategy
from .walkforward import (
    StrategyResult,
    WalkForwardConfig,
    eval_weeks,
    predict_next_week,
    run_strategy,
    verdict,
)
from .weekly import to_weekly

MIN_WEEKLY_BARS = 30  # symbols with less history than this are skipped

TACTIC_CROSS_TR = (
    "Her hafta kapanışında model geçmiş haftalarla yeniden eğitilir; en yüksek skorlu "
    "{n} hisse eşit ağırlıkla 1 hafta tutulur. Başarı ölçüsü: kıyasa ({bench}) göre "
    "maliyet sonrası fazla getiri. Bu bir analizdir, otomatik emir değildir."
)
TACTIC_TS_TR = (
    "Her hafta kapanışında model {sym} hissesinin yalnızca kendi geçmişiyle yeniden eğitilir; "
    "tahmin pozitifse hisse 1 hafta tutulur (LONG), değilse nakitte beklenir (FLAT). Başarı "
    "ölçüsü: {measure}. Bu bir analizdir, otomatik emir değildir."
)


def _measure_tr(benchmark: str) -> str:
    if benchmark == "none":
        return "maliyet sonrası ham getiri (kıyas verisi yok)"
    return f"kıyasa ({benchmark}) göre maliyet sonrası fazla getiri"


def _strategies_json(results: dict[str, StrategyResult], step_fields: list[str]) -> dict:
    out = {}
    for name, res in results.items():
        equity, cum = [], 1.0
        for s in res.steps:
            cum *= 1 + s.net
            equity.append({"week_end": s.hold_week_end, "cum_net": round(cum - 1, 6)})
        steps = []
        for s in res.steps:
            row = {}
            for f in step_fields:
                v = getattr(s, f)
                row[f] = round(v, 6) if isinstance(v, float) else v
            steps.append(row)
        out[name] = {"metrics": res.metrics, "equity": equity, "steps": steps}
    return out


def _meta(panel: Panel, weekly: dict, skipped: list[str], weeks: list[int], cfg: WalkForwardConfig,
          ridge_lambda: float, meta: dict | None) -> dict:
    return {
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
    }


def _weekly(daily_by_symbol: dict[str, list[OhlcvBar]]) -> tuple[dict, list[str]]:
    weekly = {s: to_weekly(bars) for s, bars in daily_by_symbol.items()}
    skipped = sorted(s for s, w in weekly.items() if len(w) < MIN_WEEKLY_BARS)
    return {s: w for s, w in weekly.items() if len(w) >= MIN_WEEKLY_BARS}, skipped


def run_research(
    daily_by_symbol: dict[str, list[OhlcvBar]],
    benchmark_daily: list[OhlcvBar] | None,
    cfg: WalkForwardConfig,
    *,
    benchmark_name: str = "XU100",
    ridge_lambda: float = 10.0,
    seed: int = 7,
    meta: dict | None = None,
) -> dict:
    """Cross-sectional mode: rank the universe each week, hold the top N."""
    weekly, skipped = _weekly(daily_by_symbol)
    bench_weekly = to_weekly(benchmark_daily) if benchmark_daily else None
    panel = build_panel(weekly, bench_weekly, benchmark_name=benchmark_name)
    weeks = eval_weeks(panel, cfg)
    results = {st.name: run_strategy(panel, st, weeks, cfg) for st in default_strategies(ridge_lambda, seed)}

    final_model = RidgeRanker(lam=ridge_lambda)
    next_week = predict_next_week(panel, final_model, cfg.top_n)
    next_week["coefficients"] = final_model.coefficients()
    next_week["note"] = "Analitik sıralama — otomatik emir değildir, gelecek garantisi yoktur."
    fresh = {st.name: st for st in default_strategies(ridge_lambda, seed)}
    strategy = select_strategy(panel, results, fresh, cfg)
    forecast = None
    if strategy.get("chosen"):
        all_weeks = eval_weeks(panel, replace(cfg, holdout_weeks=0, segment="validation"))
        chosen = {st.name: st for st in default_strategies(ridge_lambda, seed)}[strategy["chosen"]]
        forecast = build_forecast(panel, chosen, all_weeks, cfg.top_n)
        forecast["strategy"] = strategy["chosen"]

    return {
        "mode": "cross_section",
        "generated_at": datetime.now(UTC).isoformat(),
        "meta": _meta(panel, weekly, skipped, weeks, cfg, ridge_lambda, meta),
        "tactic_tr": TACTIC_CROSS_TR.format(n=cfg.top_n, bench=panel.benchmark),
        "verdict": verdict(results),
        "strategies": _strategies_json(
            results, ["signal_week_end", "hold_week_end", "train_max_week", "week", "top", "net", "ic"]
        ),
        "next_week": next_week,
        "strategy": strategy,
        "forecast": forecast,
    }


def run_timeseries_research(
    daily: list[OhlcvBar],
    symbol: str,
    benchmark_daily: list[OhlcvBar] | None,
    cfg: WalkForwardConfig,
    *,
    benchmark_name: str = "BENCH",
    ridge_lambda: float = 10.0,
    seed: int = 7,
    meta: dict | None = None,
) -> dict:
    """Single-stock mode: predict one stock's next week from its own history."""
    weekly, skipped = _weekly({symbol: daily})
    if not weekly:
        raise ValueError(f"{symbol}: fewer than {MIN_WEEKLY_BARS} weeks of history")
    bench_weekly = to_weekly(benchmark_daily) if benchmark_daily else None
    panel = build_panel(weekly, bench_weekly, benchmark_name=benchmark_name, fallback="none")
    weeks = eval_weeks(panel, cfg, min_rows=1)
    results = {st.name: run_ts_strategy(panel, st, weeks, cfg) for st in default_ts_strategies(ridge_lambda, seed)}

    final_model = TSRidge(lam=ridge_lambda)
    next_week = predict_next_week_ts(panel, final_model)
    next_week["coefficients"] = final_model.coefficients()
    next_week["note"] = "Analitik tahmin — otomatik emir değildir, gelecek garantisi yoktur."

    return {
        "mode": "timeseries",
        "generated_at": datetime.now(UTC).isoformat(),
        "meta": _meta(panel, weekly, skipped, weeks, cfg, ridge_lambda, {**(meta or {}), "symbol": symbol}),
        "tactic_tr": TACTIC_TS_TR.format(sym=symbol, measure=_measure_tr(panel.benchmark)),
        "verdict": verdict(results),
        "strategies": _strategies_json(
            results,
            ["signal_week_end", "hold_week_end", "train_max_week", "week", "score", "position", "outcome", "net"],
        ),
        "next_week": next_week,
    }
