"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, apiPost, directionColor, WatchlistRow } from "../../lib/api";

function StatusBadge({ status }: { status: string | null }) {
  const s = (status || "DELAYED").toLowerCase();
  return <span className={`badge ${s}`}>{status || "DELAYED"}</span>;
}

export default function DashboardPage() {
  const [rows, setRows] = useState<WatchlistRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setRows(await apiGet<WatchlistRow[]>("/watchlist"));
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [load]);

  const refresh = async () => {
    setRefreshing(true);
    try {
      await apiPost("/refresh", {});
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="container">
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <h1>Dashboard</h1>
        <button className="pill" onClick={refresh} disabled={refreshing} style={{ marginLeft: "auto", cursor: "pointer" }}>
          {refreshing ? "Refreshing…" : "Refresh now"}
        </button>
      </div>
      <p className="muted">Flow Score is the strength of current evidence, not a probability of rising.</p>
      {error && <div className="warn">API error: {error}. Is the API running? Try “Refresh now”.</div>}
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Price</th>
              <th>Change</th>
              <th>Vol 5m</th>
              <th>Flow 5m</th>
              <th>Flow 15m</th>
              <th>Score</th>
              <th>Signal</th>
              <th>Data</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.symbol}>
                <td><Link href={`/stocks/${r.symbol}`} style={{ fontWeight: 600 }}>{r.symbol}</Link></td>
                <td>{r.price?.toFixed(2) ?? "—"}</td>
                <td style={{ color: (r.change_percent ?? 0) >= 0 ? "var(--green)" : "var(--red)" }}>
                  {r.change_percent != null ? `${r.change_percent.toFixed(2)}%` : "—"}
                </td>
                <td>{r.volume_ratio_5m != null ? `${r.volume_ratio_5m.toFixed(1)}x` : "—"}</td>
                <td>{r.flow_5m != null ? r.flow_5m.toFixed(0) : "—"}</td>
                <td>{r.flow_15m != null ? r.flow_15m.toFixed(0) : "—"}</td>
                <td className="score" style={{ fontSize: 16 }}>{r.score != null ? r.score.toFixed(0) : "—"}</td>
                <td style={{ color: directionColor(r.direction, r.data_status), fontWeight: 600 }}>{r.direction ?? "—"}</td>
                <td><StatusBadge status={r.data_status} /></td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={9} className="muted">No data yet. Click “Refresh now” to ingest the first cycle.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
