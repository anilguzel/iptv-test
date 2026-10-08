import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "BIST Intelligence",
  description: "Delayed BIST market intelligence & alerting (analysis only, not trade execution).",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body>
        <nav className="nav">
          <span className="brand">BIST Intelligence</span>
          <Link href="/dashboard">Dashboard</Link>
          <Link href="/critical-moves">Critical Moves</Link>
          <span className="muted" style={{ marginLeft: "auto", fontSize: 12 }}>
            Analysis & alerting only — no automatic trade execution
          </span>
        </nav>
        {children}
      </body>
    </html>
  );
}
