"use client";

import { useEffect, useState } from "react";
import { apiGet } from "../../lib/api";

type Metrics = {
  weeks: number;
  mean_weekly_net: number;
  hit_rate: number;
  sharpe_annualised: number | null;
  cumulative_net: number;
  max_drawdown: number;
  mean_ic: number | null;
  ic_tstat: number | null;
  consistency_13w: number | null;
  exposure?: number;
};
type Strategy = { metrics: Metrics; equity: { week_end: string; cum_net: number }[] };
type ListedReport = { name: string; mode: string; source: string; universe: string | null; generated_at: string; passed: boolean };
type NextWeek = {
  as_of_week_end: string;
  coefficients: Record<string, number>;
  note: string;
  picks?: { symbol: string; score: number }[];
  symbol?: string;
  position?: "LONG" | "FLAT";
  predicted_excess?: number;
};
type Report = {
  available: boolean;
  how_to_run?: string;
  name?: string;
  mode?: "cross_section" | "timeseries";
  meta?: any;
  tactic_tr?: string;
  verdict?: { best_baseline: string | null; models: Record<string, { passed: boolean; summary_tr: string; checks: Record<string, boolean> }> };
  strategies?: Record<string, Strategy>;
  next_week?: NextWeek;
};

const COLORS: Record<string, string> = {
  ridge: "#7aa2f7", momentum_12w: "#1f9d55", momentum_4w: "#1f9d55",
  reversal_1w: "#d6a01f", always_long: "#d6a01f", random: "#8a8f98",
};
const pct = (v: number | null | undefined, d = 2) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`);
const num = (v: number | null | undefined, d = 2) => (v == null ? "—" : v.toFixed(d));

function EquityChart({ strategies }: { strategies: Record<string, Strategy> }) {
  const w = 900, h = 220, pad = 30;
  const series = Object.entries(strategies);
  const all = series.flatMap(([, s]) => s.equity.map((p) => p.cum_net));
  if (!all.length) return null;
  const lo = Math.min(0, ...all), hi = Math.max(0, ...all);
  const n = Math.max(...series.map(([, s]) => s.equity.length));
  const x = (i: number) => pad + (i * (w - 2 * pad)) / Math.max(n - 1, 1);
  const y = (v: number) => h - pad - ((v - lo) / (hi - lo || 1)) * (h - 2 * pad);
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`}>
      <line x1={pad} x2={w - pad} y1={y(0)} y2={y(0)} stroke="#3a3f4b" strokeDasharray="4" />
      <text x={4} y={y(0) + 4} fill="#8a8f98" fontSize="10">0%</text>
      {series.map(([name, s]) => (
        <path key={name} fill="none" stroke={COLORS[name] || "#ccc"} strokeWidth={name === "ridge" ? 2.5 : 1.5}
          d={s.equity.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.cum_net).toFixed(1)}`).join(" ")} />
      ))}
    </svg>
  );
}

export default function ResearchPage() {
  const [reports, setReports] = useState<ListedReport[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [r, setR] = useState<Report | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    apiGet<ListedReport[]>("/research/reports")
      .then((list) => {
        setReports(list);
        if (list.length) setSelected(list[0].name);
        else setR({ available: false, how_to_run: "python -m bist_core.research --source bist --universe BIST30 --years 3" });
      })
      .catch((e) => setErr(String(e)));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setR(null);
    apiGet<Report>(`/research?name=${encodeURIComponent(selected)}`).then(setR).catch((e) => setErr(String(e)));
  }, [selected]);

  if (err) return <div className="container"><div className="warn">API error: {err}</div></div>;
  if (r && !r.available)
    return (
      <div className="container">
        <h1>Weekly research</h1>
        <p className="muted">No report yet. Run:</p>
        <pre className="card">{r.how_to_run}</pre>
      </div>
    );

  const ts = r?.mode === "timeseries";
  const m = r?.meta;
  return (
    <div className="container">
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <h1 style={{ marginRight: "auto" }}>Weekly walk-forward research</h1>
        {reports.length > 0 && (
          <select value={selected ?? ""} onChange={(e) => setSelected(e.target.value)}
            style={{ background: "var(--panel)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 10px" }}>
            {reports.map((rep) => (
              <option key={rep.name} value={rep.name}>
                {rep.name} · {rep.mode === "timeseries" ? "single stock" : "ranking"} · {rep.source} · {rep.passed ? "PASS" : "FAIL"}
              </option>
            ))}
          </select>
        )}
      </div>

      {!r ? <p className="muted">Loading…</p> : (
        <>
          {m.data_warning && <div className="warn">{m.data_warning}</div>}
          <p className="muted" style={{ fontSize: 13 }}>
            {ts ? `single stock ${m.symbol}` : `ranking ${m.symbols_used.length} symbols`} · source {m.source} · benchmark {m.benchmark_used} ·
            {" "}{m.first_week_end} → {m.last_week_end} · {m.evaluated_weeks} out-of-sample weeks · cost {m.config.cost_bps_per_side} bps/side ·
            {" "}segment {m.segment}{m.holdout_locked ? " (holdout locked)" : ""}
          </p>
          {m.missing?.length > 0 && (
            <p className="muted" style={{ fontSize: 12 }}>Missing: {m.missing.map((x: any) => x.symbol).join(", ")}</p>
          )}
          {m.jump_warnings?.length > 0 && (
            <div className="warn" style={{ fontSize: 12, marginTop: 8 }}>
              Large one-day moves — check for unadjusted splits:{" "}
              {m.jump_warnings.slice(0, 8).map((j: any) => `${j.symbol} ${j.date} ${(j.change * 100).toFixed(0)}%`).join(" · ")}
            </div>
          )}

          {r.verdict && Object.entries(r.verdict.models).map(([name, v]) => (
            <div className="card" key={name} style={{ borderColor: v.passed ? "var(--green)" : "var(--red)", marginTop: 12 }}>
              <strong style={{ color: v.passed ? "var(--green)" : "var(--red)" }}>{name}: {v.passed ? "PASS" : "FAIL"}</strong>
              <p style={{ margin: "6px 0" }}>{v.summary_tr}</p>
              <div className="muted" style={{ fontSize: 12 }}>
                {Object.entries(v.checks).map(([k, ok]) => <span key={k} style={{ marginRight: 12 }}>{ok ? "✓" : "✗"} {k}</span>)}
              </div>
            </div>
          ))}
          <p className="muted" style={{ fontSize: 13 }}>{r.tactic_tr}</p>

          <div className="card">
            <h3>Cumulative net {m.benchmark_used === "none" ? "" : "excess "}return (out of sample)</h3>
            <EquityChart strategies={r.strategies!} />
            <div style={{ fontSize: 12 }}>
              {Object.keys(r.strategies!).map((k) => <span key={k} style={{ color: COLORS[k], marginRight: 14 }}>■ {k}</span>)}
            </div>
          </div>

          <div className="card">
            <table>
              <thead><tr>
                <th>Strategy</th><th>Mean / wk</th><th>{ts ? "Direction hit" : "Hit"}</th><th>Sharpe</th><th>Cumulative</th>
                <th>Max DD</th><th>IC</th><th>IC t</th><th>Consistency 13w</th>{ts && <th>Exposure</th>}
              </tr></thead>
              <tbody>
                {Object.entries(r.strategies!).map(([name, s]) => (
                  <tr key={name}>
                    <td style={{ color: COLORS[name], fontWeight: 600 }}>{name}</td>
                    <td>{pct(s.metrics.mean_weekly_net)}</td><td>{pct(s.metrics.hit_rate, 0)}</td>
                    <td>{num(s.metrics.sharpe_annualised)}</td><td>{pct(s.metrics.cumulative_net, 1)}</td>
                    <td>{pct(s.metrics.max_drawdown, 1)}</td><td>{num(s.metrics.mean_ic, 3)}</td>
                    <td>{num(s.metrics.ic_tstat)}</td><td>{num(s.metrics.consistency_13w)}</td>
                    {ts && <td>{pct(s.metrics.exposure, 0)}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted" style={{ fontSize: 12 }}>
              {ts
                ? "IC = correlation over time between the model's prediction and next week's excess return; its t uses an autocorrelation-adjusted sample size. Exposure = share of weeks held LONG."
                : "IC = rank correlation between the model's scores and next week's realised excess returns."}{" "}
              Judge by IC t ≥ 2, not by attractive returns alone: with several strategies, one can look great by luck.
            </p>
          </div>

          {r.next_week && (
            <div className="grid">
              <div className="card">
                <h3>Next week</h3>
                <div className="muted" style={{ fontSize: 12 }}>as of {r.next_week.as_of_week_end}</div>
                {ts ? (
                  <p style={{ fontSize: 18 }}>
                    {r.next_week.symbol}:{" "}
                    <strong style={{ color: r.next_week.position === "LONG" ? "var(--green)" : "var(--muted)" }}>{r.next_week.position}</strong>{" "}
                    <span className="muted">(predicted excess {pct(r.next_week.predicted_excess)})</span>
                  </p>
                ) : (
                  <ol>{r.next_week.picks!.map((p) => <li key={p.symbol}>{p.symbol} <span className="muted">({p.score.toFixed(3)})</span></li>)}</ol>
                )}
                <div className="muted" style={{ fontSize: 12 }}>{r.next_week.note}</div>
              </div>
              <div className="card">
                <h3>What the model learned</h3>
                <table><tbody>
                  {Object.entries(r.next_week.coefficients).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).map(([k, v]) => (
                    <tr key={k}><td>{k}</td><td style={{ color: v >= 0 ? "var(--green)" : "var(--red)" }}>{v.toFixed(4)}</td></tr>
                  ))}
                </tbody></table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
