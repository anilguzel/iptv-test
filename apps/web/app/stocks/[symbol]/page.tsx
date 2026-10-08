"use client";

import { useEffect, useState } from "react";
import { apiGet, directionColor } from "../../../lib/api";

type Detail = any;

function Timeline({ points }: { points: { timestamp: string; score: number; direction: string }[] }) {
  if (!points.length) return <p className="muted">No signal history yet.</p>;
  const w = 600, h = 120, pad = 10;
  const xs = points.map((_, i) => pad + (i * (w - 2 * pad)) / Math.max(points.length - 1, 1));
  const ys = points.map((p) => h - pad - (p.score / 100) * (h - 2 * pad));
  const path = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(" ");
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ maxWidth: 600 }}>
      <line x1={pad} y1={h - pad - (60 / 100) * (h - 2 * pad)} x2={w - pad} y2={h - pad - (60 / 100) * (h - 2 * pad)} stroke="#2a3a2a" strokeDasharray="4" />
      <line x1={pad} y1={h - pad - (40 / 100) * (h - 2 * pad)} x2={w - pad} y2={h - pad - (40 / 100) * (h - 2 * pad)} stroke="#3a2a2a" strokeDasharray="4" />
      <path d={path} fill="none" stroke="#7aa2f7" strokeWidth={2} />
      {points.map((p, i) => (
        <circle key={i} cx={xs[i]} cy={ys[i]} r={3} fill={directionColor(p.direction, null)} />
      ))}
    </svg>
  );
}

export default function StockPage({ params }: { params: { symbol: string } }) {
  const symbol = params.symbol.toUpperCase();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [ai, setAi] = useState<any | null>(null);
  const [bt, setBt] = useState<any | null>(null);

  useEffect(() => {
    apiGet(`/stocks/${symbol}`).then(setDetail).catch(() => setDetail(null));
    apiGet(`/stocks/${symbol}/ai`).then(setAi).catch(() => setAi(null));
    apiGet(`/backtest/${symbol}`).then(setBt).catch(() => setBt(null));
  }, [symbol]);

  if (!detail) return <div className="container"><p className="muted">Loading {symbol}…</p></div>;

  const sig = detail.signal;
  const q = detail.quote;
  return (
    <div className="container">
      <h1>{symbol}</h1>
      <div className="warn">
        Data status: <b>{q?.data_status ?? "?"}</b> via {q?.provider ?? "?"} · market time {q?.market_timestamp ?? "—"} ·
        latency {q?.latency != null ? `${(q.latency * 1000).toFixed(0)}ms` : "—"}. Delayed data — not LIVE.
      </div>

      <div className="grid">
        <div className="card">
          <div className="muted">Price</div>
          <div className="score">{q?.price?.toFixed(2) ?? "—"}</div>
          <div style={{ color: (q?.change_percent ?? 0) >= 0 ? "var(--green)" : "var(--red)" }}>
            {q?.change_percent != null ? `${q.change_percent.toFixed(2)}%` : "—"}
          </div>
        </div>
        <div className="card">
          <div className="muted">Flow Score (evidence strength)</div>
          <div className="score" style={{ color: directionColor(sig?.direction, q?.data_status) }}>
            {sig ? sig.score.toFixed(0) : "—"}/100
          </div>
          <div>{sig?.direction ?? "—"} · {sig?.change ?? ""}</div>
          <div className="muted">confidence {sig ? `${(sig.confidence * 100).toFixed(0)}%` : "—"}</div>
        </div>
        <div className="card">
          <div className="muted">Technical</div>
          <div style={{ fontSize: 13 }}>
            RSI14: {detail.technical?.rsi_14?.toFixed(1) ?? "—"}<br />
            EMA9: {detail.technical?.ema_9?.toFixed(2) ?? "—"}<br />
            SMA20: {detail.technical?.sma_20?.toFixed(2) ?? "—"}<br />
            VWAP: {detail.technical?.vwap?.toFixed(2) ?? "—"}<br />
            ATR14: {detail.technical?.atr_14?.toFixed(2) ?? "—"}
          </div>
        </div>
        <div className="card">
          <div className="muted">Rolling flow (proxy)</div>
          <div style={{ fontSize: 13 }}>
            1m: {detail.flow?.flow_1m?.toFixed(0) ?? "—"}<br />
            5m: {detail.flow?.flow_5m?.toFixed(0) ?? "—"}<br />
            15m: {detail.flow?.flow_15m?.toFixed(0) ?? "—"}<br />
            60m: {detail.flow?.flow_60m?.toFixed(0) ?? "—"}<br />
            accel: {detail.flow?.flow_acceleration?.toFixed(0) ?? "—"}
          </div>
        </div>
      </div>

      <div className="card">
        <h3>Signal timeline</h3>
        <Timeline points={detail.signal_timeline ?? []} />
      </div>

      <div className="card">
        <h3>AI analysis</h3>
        {!ai || ai.summary === "data_unavailable" ? (
          <p className="muted">data_unavailable</p>
        ) : (
          <div style={{ fontSize: 14 }}>
            <p>{ai.summary}</p>
            <p><b>Momentum:</b> {ai.momentum}</p>
            <p><b>Buying pressure:</b></p>
            <ul className="clean">{(ai.buying_pressure || []).map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
            <p><b>Selling pressure:</b></p>
            <ul className="clean">{(ai.selling_pressure || []).map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
            <p><b>Risks:</b></p>
            <ul className="clean">{(ai.risks || []).map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
            <p><b>Invalidation:</b></p>
            <ul className="clean">{(ai.invalidation_conditions || []).map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
            <p><b>Next trigger:</b> {ai.next_trigger}</p>
            <p className="muted">News: {(ai.news_context || []).join("; ")}</p>
          </div>
        )}
      </div>

      <div className="grid">
        <div className="card">
          <h3>Anomalies</h3>
          {(detail.anomalies ?? []).length === 0 ? <p className="muted">none</p> : (
            <ul className="clean">
              {detail.anomalies.map((a: any, i: number) => (
                <li key={i}><span className="pill">{a.severity}</span> {a.type}: {a.evidence}</li>
              ))}
            </ul>
          )}
        </div>
        <div className="card">
          <h3>News</h3>
          {(detail.news ?? []).length === 0 ? <p className="muted">Mevcut veri kaynaklarında yeni haber tespit edilmedi.</p> : (
            <ul className="clean">
              {detail.news.map((n: any, i: number) => <li key={i}>[{n.category}] {n.headline}</li>)}
            </ul>
          )}
        </div>
        <div className="card">
          <h3>Backtest (30m horizon)</h3>
          {!bt || !bt.signal_count ? <p className="muted">insufficient stored signals/prices</p> : (
            <div style={{ fontSize: 13 }}>
              signals: {bt.signal_count}<br />
              win rate: {(bt.win_rate * 100).toFixed(0)}%<br />
              avg return: {(bt.average_return * 100).toFixed(2)}%<br />
              median: {(bt.median_return * 100).toFixed(2)}%<br />
              max drawdown: {(bt.max_drawdown * 100).toFixed(2)}%<br />
              profit factor: {bt.profit_factor ?? "∞"}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
