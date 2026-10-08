"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, directionColor } from "../../lib/api";

type Move = {
  id: number;
  timestamp: string;
  symbol: string;
  score: number;
  direction: string;
  change: string;
  evidence: string[];
  data_snapshot: any;
};

export default function CriticalMovesPage() {
  const [moves, setMoves] = useState<Move[]>([]);
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    const load = () => apiGet<Move[]>("/critical-moves").then(setMoves).catch(() => setMoves([]));
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="container">
      <h1>Critical Moves</h1>
      <p className="muted">Chronological signal changes. Click an event to inspect the exact data snapshot used.</p>
      {moves.length === 0 && <p className="muted">No critical moves recorded yet.</p>}
      {moves.map((m) => (
        <div className="card" key={m.id}>
          <div style={{ display: "flex", gap: 12, alignItems: "center", cursor: "pointer" }} onClick={() => setOpen(open === m.id ? null : m.id)}>
            <span className="muted" style={{ fontVariantNumeric: "tabular-nums" }}>{new Date(m.timestamp).toLocaleString()}</span>
            <Link href={`/stocks/${m.symbol}`} style={{ fontWeight: 700 }}>{m.symbol}</Link>
            <span style={{ color: directionColor(m.direction, null), fontWeight: 600 }}>{m.direction}</span>
            <span className="pill">{m.change}</span>
            <span className="score" style={{ fontSize: 16, marginLeft: "auto" }}>Score {m.score.toFixed(0)}</span>
          </div>
          {m.evidence?.length > 0 && (
            <ul className="clean" style={{ marginTop: 8 }}>{m.evidence.slice(0, 4).map((e, i) => <li key={i}>{e}</li>)}</ul>
          )}
          {open === m.id && (
            <pre style={{ background: "#0b0d11", padding: 12, borderRadius: 8, overflow: "auto", fontSize: 12 }}>
              {JSON.stringify(m.data_snapshot, null, 2)}
            </pre>
          )}
        </div>
      ))}
    </div>
  );
}
