"""Pick one strategy from the past, then use it for next week.

The rule is fixed in code, so nothing is hand-tuned on the outcome:

1. Every candidate strategy is walked forward over the validation weeks
   (each week trained only on the weeks before it).
2. A candidate is eligible when its mean weekly net excess return is positive
   and above the random ranking's.
3. The eligible candidate with the highest t-statistic of weekly net returns
   (mean / standard error) is chosen. If none is eligible, the choice is to
   hold the benchmark and pick no stocks.
4. The chosen strategy is then run once on the most recent holdout weeks,
   which played no part in the choice. That is the out-of-sample check.

Confidence:
- GÜÇLÜ: t above the multiple-testing threshold (one-sided 5%, Bonferroni over
  the candidates) and positive on the holdout.
- ORTA: t significant for a single test (one-sided 5%) and positive on the
  holdout, but not after accounting for how many strategies were tried.
- ZAYIF: eligible on the past, but not significant or negative on the
  holdout. On pure noise about half of all runs land here: it is not evidence.
- YOK: no candidate beat the benchmark and random after costs.
"""
from __future__ import annotations

import math
from dataclasses import replace
from statistics import NormalDist

import numpy as np

from .features import Panel
from .walkforward import StrategyResult, WalkForwardConfig, eval_weeks, predict_next_week, run_strategy

SIGNIFICANCE = 0.05
CONTROL = "random"

STRATEGY_TR = {
    "ridge": "8 göstergeyi birlikte tartan öğrenen model",
    "momentum_12w": "son 12 haftada kıyasa göre en çok yükselenleri al (momentum)",
    "momentum_4w": "son 4 haftada kıyasa göre en çok yükselenleri al (kısa momentum)",
    "reversal_1w": "geçen hafta en çok düşenleri al (tepki alımı)",
    "low_vol_12w": "son 12 haftada en az dalgalananları al (düşük oynaklık)",
    "near_high_12w": "12 haftalık zirvesine en yakın olanları al",
}


def tstat(net: np.ndarray) -> float | None:
    if len(net) < 2:
        return None
    sd = float(net.std(ddof=1))
    return float(net.mean() / (sd / math.sqrt(len(net)))) if sd > 0 else None


def significance_threshold(n_candidates: int, alpha: float = SIGNIFICANCE) -> float:
    return NormalDist().inv_cdf(1 - alpha / max(n_candidates, 1))


def _nets(result: StrategyResult) -> np.ndarray:
    return np.array([s.net for s in result.steps])


def select_strategy(
    panel: Panel,
    results: dict[str, StrategyResult],
    fresh_strategies: dict,
    cfg: WalkForwardConfig,
) -> dict:
    """Choose a strategy from validation results; confirm on the holdout; rank next week."""
    candidates = {n: r for n, r in results.items() if n != CONTROL}
    control = results[CONTROL].metrics.get("mean_weekly_net") if CONTROL in results else None
    threshold = significance_threshold(len(candidates))

    table = []
    for name, r in candidates.items():
        net = _nets(r)
        t = tstat(net)
        mean = float(net.mean()) if len(net) else None
        eligible = mean is not None and mean > 0 and (control is None or mean > control)
        table.append({"strategy": name, "mean_weekly_net": None if mean is None else round(mean, 6),
                      "tstat": None if t is None else round(t, 3), "eligible": bool(eligible)})
    table.sort(key=lambda row: -(row["tstat"] if row["tstat"] is not None else -math.inf))

    eligible = [row for row in table if row["eligible"] and row["tstat"] is not None]
    out: dict = {
        "rule": "geçmişte (doğrulama haftaları) maliyet sonrası pozitif ve rastgeleden iyi olanlar içinde "
                "en yüksek t-istatistikli strateji; son haftalarda (holdout) ayrıca test edilir",
        "candidates": table,
        "control_mean_weekly_net": control,
        "significance_threshold": round(threshold, 3),
    }
    if not eligible:
        out.update({
            "chosen": None,
            "confidence": "YOK",
            "summary_tr": f"Hiçbir strateji geçmişte maliyet sonrası kıyası ({panel.benchmark}) ve rastgele "
                          "seçimi yenemedi. Öneri: hisse seçme, kıyas endeksini tut ya da bekle.",
            "next_week": None,
        })
        return out

    best = eligible[0]
    name = best["strategy"]
    past = results[name]

    holdout = None
    if cfg.segment == "validation" and cfg.holdout_weeks:
        weeks = eval_weeks(panel, replace(cfg, segment="holdout", unlock_holdout=True))
        h = run_strategy(panel, fresh_strategies[name], weeks, cfg)
        hn = _nets(h)
        holdout = {
            "weeks": len(hn),
            "from": h.steps[0].hold_week_end if h.steps else None,
            "to": h.steps[-1].hold_week_end if h.steps else None,
            "mean_weekly_net": round(float(hn.mean()), 6) if len(hn) else None,
            "cumulative_net": h.metrics.get("cumulative_net"),
            "hit_rate": h.metrics.get("hit_rate"),
        }
    holdout_ok = bool(holdout and holdout["mean_weekly_net"] is not None and holdout["mean_weekly_net"] > 0)
    if best["tstat"] >= threshold and holdout_ok:
        confidence = "GÜÇLÜ"
    elif best["tstat"] >= NormalDist().inv_cdf(1 - SIGNIFICANCE) and holdout_ok:
        confidence = "ORTA"
    else:
        confidence = "ZAYIF"

    all_net = np.concatenate([_nets(past)] + ([_nets(h)] if holdout else []))
    lo, hi = (float(np.percentile(all_net, q)) for q in (10, 90))
    picks = predict_next_week(panel, fresh_strategies[name], cfg.top_n)
    out.update({
        "chosen": name,
        "description_tr": STRATEGY_TR.get(name, name),
        "confidence": confidence,
        "past": {
            "weeks": past.metrics.get("weeks"),
            "from": past.steps[0].hold_week_end if past.steps else None,
            "to": past.steps[-1].hold_week_end if past.steps else None,
            "mean_weekly_net": best["mean_weekly_net"],
            "tstat": best["tstat"],
            "cumulative_net": past.metrics.get("cumulative_net"),
            "max_drawdown": past.metrics.get("max_drawdown"),
            "hit_rate": past.metrics.get("hit_rate"),
        },
        "holdout": holdout,
        "summary_tr": _summary(name, confidence, best, threshold, holdout, panel.benchmark),
        "next_week": {
            "as_of_week_end": picks["as_of_week_end"],
            "picks": [p["symbol"] for p in picks["picks"]],
            "expected_weekly_excess": best["mean_weekly_net"],
            "typical_range": [round(lo, 6), round(hi, 6)],
            "note": "Beklenen değer geçmiş ortalamadır; aralık geçmiş haftaların %10-%90 dilimidir. "
                    "Garanti değildir, otomatik emir değildir.",
        },
    })
    return out


def _summary(name: str, confidence: str, best: dict, threshold: float, holdout: dict | None, bench: str) -> str:
    text = (f"Geçmişe göre en iyi strateji: {STRATEGY_TR.get(name, name)}. Kıyasa ({bench}) göre haftada "
            f"ortalama {best['mean_weekly_net'] * 100:+.2f}% (maliyet sonrası), t={best['tstat']:.2f} "
            f"(anlamlılık eşiği {threshold:.2f}).")
    if holdout and holdout["mean_weekly_net"] is not None:
        text += (f" Seçimde kullanılmayan son {holdout['weeks']} haftada haftalık "
                 f"{holdout['mean_weekly_net'] * 100:+.2f}%.")
    text += {
        "GÜÇLÜ": " Güven: GÜÇLÜ.",
        "ORTA": " Güven: ORTA — avantaj var gibi, ama birden çok strateji denendiği için şans olma ihtimali dışlanamıyor.",
        "ZAYIF": " Güven: ZAYIF — istatistiksel olarak şanstan ayırt edilemiyor; sinyal sayılmaz.",
    }[confidence]
    return text
