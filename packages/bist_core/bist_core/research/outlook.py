"""Two forecasts the weekly research showed are worth making.

1. **Risk** (how much a stock will move next week, not which way). Last
   week's range and the recent volatility of weekly returns rank next week's
   move size well out of sample, unlike the direction. A linear model on those
   three numbers, refitted every few weeks on earlier weeks only, gives each
   stock an expected move size; the 10th/90th percentiles of past moves
   divided by that size turn it into a range that held about 80% of the time.

2. **Medium-term ranking** (3 and 6 months). Rankings are measured against
   the equal-weighted average of the same stocks, so a universe of today's
   large caps (which all beat the index in hindsight) cannot make a rule look
   good. Holding periods do not overlap, so each period is one independent
   observation and the t-statistics are honest. The best rule must clear a
   multiple-testing threshold over every rule and horizon tried, and its last
   two years are reported separately.

Analysis only: nothing here places orders.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime
from statistics import NormalDist

import numpy as np

from ..schemas import OhlcvBar
from .features import FEATURE_NAMES, build_panel
from .models import BoostedRanker, RidgeRanker, boosting_available
from .weekly import to_weekly

RISK_LOOKBACK = 12
RISK_MIN_TRAIN_WEEKS = 52
RISK_REFIT_EVERY = 4
BAND = (0.1, 0.9)

HORIZONS = (13, 26)
RECENT_WEEKS = 104
CONTROL = "random"
SIGNIFICANCE = 0.05

RULE_TR = {
    "momentum_12w": "son 12 haftada grubundan en çok yükselenler",
    "near_high_12w": "12 haftalık zirvesine en yakın olanlar",
    "low_vol_12w": "en az dalgalananlar",
    "reversal_4w": "son 4 haftada en çok düşenler",
    "ridge": "göstergeleri birlikte tartan doğrusal model",
    "boosting": "kendi kurallarını öğrenen model",
}


# --------------------------------------------------------------------------- #
# Risk
# --------------------------------------------------------------------------- #
def _spearman(a: np.ndarray, b: np.ndarray) -> float | None:
    if len(a) < 5:
        return None
    ra, rb = a.argsort().argsort(), b.argsort().argsort()
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def _risk_rows(weekly_by_symbol: dict) -> tuple[list[str], list[str], list[dict]]:
    """One row per (stock, week) with the three predictors and next week's return."""
    calendar = sorted({b.week for bars in weekly_by_symbol.values() for b in bars})
    index = {w: i for i, w in enumerate(calendar)}
    week_end = [""] * len(calendar)
    rows: list[dict] = []
    for sym, bars in weekly_by_symbol.items():
        for b in bars:
            i = index[b.week]
            week_end[i] = max(week_end[i], b.end_date.isoformat())
        closes = np.array([b.close for b in bars])
        rets = np.full(len(bars), np.nan)
        rets[1:] = closes[1:] / closes[:-1] - 1
        for k in range(RISK_LOOKBACK, len(bars)):
            win = rets[k - RISK_LOOKBACK + 1:k + 1]
            if not np.isfinite(win).all():
                continue
            b = bars[k]
            nxt = float(rets[k + 1]) if k + 1 < len(bars) and index[bars[k + 1].week] == index[b.week] + 1 else math.nan
            rows.append({
                "symbol": sym, "week": index[b.week], "close": b.close,
                "x": [float(win[-4:].std()), float(win.std()), float((b.high - b.low) / b.close)],
                "ret": nxt,
            })
    return calendar, week_end, rows


def _fit_risk(X: np.ndarray, absr: np.ndarray, r: np.ndarray):
    A = np.hstack([np.ones((len(X), 1)), X])
    w, *_ = np.linalg.lstsq(A, absr, rcond=None)
    size = np.maximum(A @ w, 0.005)
    z = r / size
    return w, float(np.quantile(z, BAND[0])), float(np.quantile(z, BAND[1]))


def _predict_size(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    return np.maximum(np.hstack([np.ones((len(X), 1)), X]) @ w, 0.005)


def risk_forecast(weekly_by_symbol: dict) -> dict:
    _, week_end, rows = _risk_rows(weekly_by_symbol)
    if not rows:
        return {"error": "veri yok"}
    wk = np.array([r["week"] for r in rows])
    X = np.array([r["x"] for r in rows])
    ret = np.array([r["ret"] for r in rows])
    known = np.isfinite(ret)
    weeks = sorted(set(wk[known].tolist()))[RISK_MIN_TRAIN_WEEKS:]

    ics, base_ics, inside = [], [], []
    model = None
    for n, t in enumerate(weeks):
        if model is None or n % RISK_REFIT_EVERY == 0:
            tr = known & (wk < t)
            model = _fit_risk(X[tr], np.abs(ret[tr]), ret[tr])
        w, zlo, zhi = model
        m = known & (wk == t)
        size = _predict_size(w, X[m])
        ic = _spearman(size, np.abs(ret[m]))
        base = _spearman(X[m][:, 1], np.abs(ret[m]))
        if ic is not None:
            ics.append(ic)
        if base is not None:
            base_ics.append(base)
        inside.extend(((ret[m] >= zlo * size) & (ret[m] <= zhi * size)).tolist())

    def tstat(a):
        a = np.array(a)
        return round(float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))), 2) if len(a) > 1 and a.std() > 0 else None

    w, zlo, zhi = _fit_risk(X[known], np.abs(ret[known]), ret[known])
    latest = int(wk.max())
    cur = [r for r in rows if r["week"] == latest]
    sizes = _predict_size(w, np.array([r["x"] for r in cur]))
    order = np.argsort(-sizes)
    stocks = []
    for rank, i in enumerate(order, start=1):
        r, s = cur[i], float(sizes[i])
        stocks.append({
            "risk_rank": rank, "symbol": r["symbol"], "close": round(r["close"], 4),
            "expected_move": round(s, 6),
            "range_low": round(zlo * s, 6), "range_high": round(zhi * s, 6),
            "price_low": round(r["close"] * (1 + zlo * s), 4), "price_high": round(r["close"] * (1 + zhi * s), 4),
        })
    return {
        "as_of_week_end": week_end[latest],
        "method": "Geçen haftanın fiyat aralığı ile son 4 ve 12 haftanın dalgalanmasından, sadece önceki haftalarla "
                  f"{RISK_REFIT_EVERY} haftada bir yeniden kurulan doğrusal model; aralık geçmiş hareketlerin %10-%90 dilimi.",
        "validation": {
            "weeks": len(ics),
            "mean_ic": round(float(np.mean(ics)), 4) if ics else None,
            "ic_tstat": tstat(ics),
            "ic_positive_share": round(float(np.mean(np.array(ics) > 0)), 4) if ics else None,
            "baseline_vol12_mean_ic": round(float(np.mean(base_ics)), 4) if base_ics else None,
            "band_coverage": round(float(np.mean(inside)), 4) if inside else None,
            "band_target": BAND[1] - BAND[0],
        },
        "stocks": stocks,
    }


# --------------------------------------------------------------------------- #
# Medium-term ranking
# --------------------------------------------------------------------------- #
def _forward(panel, h: int) -> np.ndarray:
    """Return over the next ``h`` weeks, in excess of the group's average (NaN if not yet known)."""
    nxt = {(s, int(w)): y for s, w, y in zip(panel.symbols, panel.week, panel.y_raw, strict=True)}
    out = np.full(len(panel.y_raw), np.nan)
    for i, (s, w) in enumerate(zip(panel.symbols, panel.week, strict=True)):
        vals = [nxt.get((s, int(w) + k)) for k in range(h)]
        if all(v is not None and np.isfinite(v) for v in vals):
            out[i] = float(np.prod([1 + v for v in vals]) - 1)
    return out


def _rank_target(panel, tgt: np.ndarray) -> np.ndarray:
    rank = np.full(len(tgt), np.nan)
    for w in np.unique(panel.week):
        m = (panel.week == w) & np.isfinite(tgt)
        n = int(m.sum())
        if n >= 2:
            rank[m] = tgt[m].argsort().argsort() / (n - 1) - 0.5
    return rank


def _strategies(seed: int):
    f = {n: i for i, n in enumerate(FEATURE_NAMES)}
    rules = {
        "momentum_12w": lambda X: X[:, f["ex_ret_12w"]],
        "near_high_12w": lambda X: X[:, f["dist_from_12w_high"]],
        "low_vol_12w": lambda X: -X[:, f["vol_12w"]],
        "reversal_4w": lambda X: -X[:, f["ex_ret_4w"]],
    }
    models = {"ridge": lambda: RidgeRanker(10.0)}
    if boosting_available():
        models["boosting"] = lambda: BoostedRanker(refit_every=1, seed=seed)
    return rules, models


def medium_term(panel, *, top_n: int = 5, cost_bps: float = 10.0, seed: int = 7,
                horizons: tuple[int, ...] = HORIZONS, start_week: int = 65) -> dict:
    rules, models = _strategies(seed)
    T = int(panel.week.max())
    results: dict[str, dict] = {}
    targets: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for h in horizons:
        tgt = _forward(panel, h)
        rank = _rank_target(panel, tgt)
        targets[h] = (tgt, rank)
        weeks = list(range(start_week, T - h + 1, h))
        for name in [*rules, *models, CONTROL]:
            rng = np.random.default_rng(seed)
            model = models[name]() if name in models else None
            prev, nets, periods = None, [], []
            for t in weeks:
                rows = (panel.week == t) & np.isfinite(tgt)
                if rows.sum() < 2 * top_n:
                    continue
                X = panel.X[rows]
                if name in rules:
                    sc = rules[name](X)
                elif name == CONTROL:
                    sc = rng.standard_normal(len(X))
                else:
                    train = (panel.week <= t - h) & np.isfinite(rank)  # targets fully known by week t
                    if train.sum() < 200:
                        continue
                    model.fit(panel.X[train], rank[train])
                    sc = model.predict(X)
                order = np.argsort(-sc, kind="stable")[:top_n]
                syms = panel.symbols[rows]
                pick = {str(s) for s in syms[order]}
                turn = 1.0 if prev is None else 1 - len(pick & prev) / top_n
                prev = pick
                net = float(tgt[rows][order].mean() - tgt[rows].mean()) - turn * 2 * cost_bps / 1e4
                nets.append(net)
                periods.append({"from": panel.week_end[t], "picks": sorted(pick), "excess": round(net, 6)})
            a = np.array(nets)
            n_recent = max(2, RECENT_WEEKS // h)
            results[f"{name}@{h}"] = {
                "strategy": name, "horizon_weeks": h, "periods": len(a),
                "mean": round(float(a.mean()), 6) if len(a) else None,
                "tstat": round(float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))), 3) if len(a) > 2 and a.std() > 0 else None,
                "hit_rate": round(float((a > 0).mean()), 4) if len(a) else None,
                "annualised": round(float((1 + a.mean()) ** (52 / h) - 1), 4) if len(a) else None,
                "recent_mean": round(float(a[-n_recent:].mean()), 6) if len(a) else None,
                "history": periods,
            }

    candidates = {k: v for k, v in results.items() if v["strategy"] != CONTROL}
    threshold = NormalDist().inv_cdf(1 - SIGNIFICANCE / max(len(candidates), 1))
    single = NormalDist().inv_cdf(1 - SIGNIFICANCE)
    eligible = []
    for k, v in candidates.items():
        ctrl = results.get(f"{CONTROL}@{v['horizon_weeks']}", {}).get("mean")
        if v["mean"] is not None and v["tstat"] is not None and v["mean"] > 0 and (ctrl is None or v["mean"] > ctrl):
            eligible.append(k)
    table = sorted(({"key": k, **{f: v[f] for f in ("strategy", "horizon_weeks", "periods", "mean", "tstat", "hit_rate",
                                                     "annualised", "recent_mean")}, "eligible": k in eligible}
                    for k, v in candidates.items()), key=lambda r: -(r["tstat"] if r["tstat"] is not None else -9))
    out = {"significance_threshold": round(threshold, 3), "candidates": table,
           "measure": "aynı hisselerin eşit ağırlıklı ortalamasına göre, maliyet sonrası"}
    if not eligible:
        out.update({"chosen": None, "confidence": "YOK",
                    "summary_tr": "Hiçbir kural 3 ya da 6 ayda grubun ortalamasını maliyet sonrası yenemedi."})
        return out

    best_key = max(eligible, key=lambda k: candidates[k]["tstat"])
    best = candidates[best_key]
    recent_ok = (best["recent_mean"] or 0) > 0
    if best["tstat"] >= threshold and recent_ok:
        confidence = "GÜÇLÜ"
    elif best["tstat"] >= single and recent_ok:
        confidence = "ORTA"
    else:
        confidence = "ZAYIF"

    h = best["horizon_weeks"]
    tgt, rank = targets[h]
    latest = int(panel.week.max())
    rows = panel.week == latest
    X = panel.X[rows]
    name = best["strategy"]
    if name in rules:
        sc = rules[name](X)
    else:
        model = models[name]()
        train = np.isfinite(rank)
        model.fit(panel.X[train], rank[train])
        sc = model.predict(X)
    order = np.argsort(-sc, kind="stable")
    syms = panel.symbols[rows]
    ranking = [{"rank": i + 1, "symbol": str(syms[j]), "pick": i < top_n} for i, j in enumerate(order)]
    recent_note = "son 2 yılda da tuttu" if recent_ok else "son 2 yılda tutmadı"
    out.update({
        "chosen": name, "chosen_horizon_weeks": h, "description_tr": RULE_TR.get(name, name),
        "confidence": confidence, "past": best | {"history": None},
        "history": best["history"],
        "as_of_week_end": panel.week_end[latest],
        "ranking": ranking,
        "summary_tr": (f"En iyi sonuç: {RULE_TR.get(name, name)}, {h} hafta tutulduğunda. Grubun ortalamasına göre dönem "
                       f"başına {best['mean'] * 100:+.1f}% (yıllık {best['annualised'] * 100:+.1f}%), {best['periods']} "
                       f"dönemin %{best['hit_rate'] * 100:.0f}'inde önde; t={best['tstat']:.2f} (eşik {threshold:.2f}); "
                       f"{recent_note}. Güven: {confidence}."),
    })
    return out


# --------------------------------------------------------------------------- #
# Move odds: how often a stock moved this much in one or three months
# --------------------------------------------------------------------------- #
ODDS_LOOKBACK_DAYS = 756  # about three years of trading days
ODDS = {21: (0.05, 0.10, 0.15), 63: (0.10, 0.20, 0.30)}  # horizon in trading days -> thresholds


def move_odds(daily_by_symbol: dict[str, list[OhlcvBar]]) -> dict:
    """Base rates from each stock's own last three years: in what share of all
    21- and 63-trading-day windows it rose or fell at least a given amount.
    History, not a prediction: the windows overlap and the period had high
    inflation, so TL prices drifted up."""
    stocks = []
    for sym, bars in sorted(daily_by_symbol.items()):
        closes = np.array([b.close for b in sorted(bars, key=lambda b: b.timestamp)][-ODDS_LOOKBACK_DAYS:])
        row: dict = {"symbol": sym}
        for h, levels in ODDS.items():
            if len(closes) <= h + 20:
                continue
            r = closes[h:] / closes[:-h] - 1
            tag = "1m" if h == 21 else "3m"
            row[f"median_{tag}"] = round(float(np.median(r)), 4)
            for lv in levels:
                row[f"up{int(lv * 100)}_{tag}"] = round(float((r >= lv).mean()), 4)
                row[f"down{int(lv * 100)}_{tag}"] = round(float((r <= -lv).mean()), 4)
            row[f"windows_{tag}"] = len(r)
        stocks.append(row)
    return {
        "lookback_trading_days": ODDS_LOOKBACK_DAYS,
        "thresholds": {"1m": list(ODDS[21]), "3m": list(ODDS[63])},
        "note": "Geçmiş 3 yılın istatistiği, tahmin değildir; o dönemde yüksek enflasyon TL fiyatlarını yukarı itti.",
        "stocks": stocks,
    }


# --------------------------------------------------------------------------- #
def run_outlook(daily_by_symbol: dict[str, list[OhlcvBar]], *, top_n: int = 5, cost_bps: float = 10.0,
                seed: int = 7, meta: dict | None = None) -> dict:
    weekly = {s: to_weekly(b) for s, b in daily_by_symbol.items()}
    weekly = {s: w for s, w in weekly.items() if len(w) >= 30}
    panel = build_panel(weekly, None, benchmark_name="universe")  # excess vs the group's own average
    return {
        "mode": "outlook",
        "generated_at": datetime.now(UTC).isoformat(),
        "meta": {"symbols_used": sorted(weekly), "top_n": top_n, "cost_bps": cost_bps, **(meta or {})},
        "risk": risk_forecast(weekly),
        "medium_term": medium_term(panel, top_n=top_n, cost_bps=cost_bps, seed=seed),
        "odds": move_odds({s: b for s, b in daily_by_symbol.items() if s in weekly}),
        "note": "Analizdir, otomatik emir değildir.",
    }
