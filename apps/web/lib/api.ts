// Centralised API client. Server-side requests use INTERNAL_API_URL (the
// docker service name); browser requests use NEXT_PUBLIC_API_URL.
export const API_BASE =
  (typeof window === "undefined"
    ? process.env.INTERNAL_API_URL
    : process.env.NEXT_PUBLIC_API_URL) || "http://localhost:8000";

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export type WatchlistRow = {
  symbol: string;
  price: number | null;
  change_percent: number | null;
  volume_ratio_5m: number | null;
  flow_5m: number | null;
  flow_15m: number | null;
  score: number | null;
  direction: string | null;
  data_status: string | null;
};

// Maps a signal direction / data status to a semantic colour.
export function directionColor(direction: string | null, dataStatus: string | null): string {
  if (dataStatus === "STALE") return "#8a8f98"; // gray
  switch (direction) {
    case "EXTREME_POSITIVE":
    case "STRONG_POSITIVE":
    case "POSITIVE":
      return "#1f9d55"; // green
    case "NEGATIVE":
    case "STRONG_NEGATIVE":
      return "#d64545"; // red
    case "WATCH":
      return "#d6a01f"; // yellow
    default:
      return "#8a8f98"; // gray / neutral
  }
}
