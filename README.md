# BIST Intelligence MVP

A personal **market intelligence & alerting** system for Borsa İstanbul (BIST).

> ⚠️ **This is an analysis and alerting system. It does NOT automatically execute
> trades.** It produces analytical signals only
> (`STRONG_POSITIVE · POSITIVE · NEUTRAL · NEGATIVE · STRONG_NEGATIVE · WATCH`),
> never claims certainty, and clearly distinguishes **delayed** data from
> real-time data.

The MVP answers questions like:
- Is there unusual activity in KTLEV?
- How many times normal is the volume?
- Is the move *accelerating* or *weakening*?
- Is the positive thesis from 15 minutes ago still valid?
- Why did the signal change?
- Did this kind of signal work historically?

## Architecture

```
 BIST Data Service (~15 min delayed)
            │
            ▼
      DATA COLLECTOR  ──►  PostgreSQL / Redis / TimescaleDB
            │
            ▼
       FLOW ENGINE      (volume / momentum / rolling flow proxies)
            │
            ▼
      SIGNAL ENGINE     (deterministic 0–100 flow score)
            │
            ▼
       AI ANALYZER      (explains the score, never computes it)
            │
     ┌──────┼───────┐
     ▼      ▼       ▼
 Dashboard Telegram  (future: Push)
```

The data source is treated as an **external provider behind an adapter**
(`MarketDataProvider`). The free open-source
[`bist-data-service`](https://github.com/Armert-Labs/bist-data-service) is
`~15 min DELAYED`, so the app **never shows `LIVE`** for it.

### Repository layout

```
apps/web/                     Next.js + TypeScript frontend
services/
  api/                        FastAPI (dashboard / detail / critical-moves / backtest / AI)
  signal_engine/              Ingestion + scoring worker loop
  notification_worker/        Telegram alerts (cooldown-aware)
packages/
  bist_core/                  Shared library — the "brain":
    providers/                MarketDataProvider adapter + Demo + News + future interfaces
    engines/                  flow, volume, scoring, anomaly, signal-change, backtest
    ai/                       AI analyzer (mock + Anthropic)
    notifications/            cooldown + telegram formatting
    db/                       SQLAlchemy models + session
    pipeline.py / runner.py   assembly + collection cycle
infrastructure/
  docker/                     Dockerfiles + python requirements
  migrations/                 TimescaleDB extension + optional hypertables
tests/                        deterministic unit tests
docker-compose.yml
.env.example
```

## Quick start (Docker)

```bash
cp .env.example .env
# The default .env uses DEMO_MODE=true (deterministic, clearly-fake data) so it
# runs with no external provider. Set DEMO_MODE=false to use the real provider.

docker compose up --build
```

Then open:
- Dashboard: http://localhost:3000/dashboard
- Critical Moves: http://localhost:3000/critical-moves
- API docs: http://localhost:8000/docs

On a fresh demo DB the first cycle runs within ~60s; you can also click
**“Refresh now”** on the dashboard (calls `POST /refresh`) to ingest immediately.

### Services started by Docker Compose
`web`, `api`, `signal-engine`, `worker`, `postgres` (TimescaleDB), `redis`.

## Using the real data source

1. Run the open-source service from
   <https://github.com/Armert-Labs/bist-data-service> (do **not** fork/modify it —
   this app treats it as an external provider).
2. In `.env`:
   ```
   DEMO_MODE=false
   MARKET_DATA_PROVIDER=bist
   BIST_DATA_SERVICE_URL=http://host.docker.internal:8000   # or its real URL
   ```
3. `docker compose up`. All quotes will be labelled **DELAYED** (or **STALE**).

## Environment variables

See [`.env.example`](.env.example). Key ones:

| Variable | Default | Purpose |
|---|---|---|
| `DEMO_MODE` | `true` | Deterministic fake data (`DataStatus=DEMO`) |
| `MARKET_DATA_PROVIDER` | `bist` | `bist` or `demo` |
| `BIST_DATA_SERVICE_URL` | — | External provider base URL |
| `POLL_INTERVAL_SECONDS` / `SIGNAL_INTERVAL_SECONDS` | `60` | Ingestion / scoring cadence |
| `STALE_AFTER_SECONDS` | `180` | Quote age that flips DELAYED→STALE |
| `AI_PROVIDER` | `mock` | `mock` (offline) or `anthropic` |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | — | Claude API for the explainer |
| `TELEGRAM_ENABLED` / `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | off | Alerts |
| `ALERT_COOLDOWN_SECONDS` | `600` | Per-symbol alert throttle (reversals bypass it) |
| `DEFAULT_WATCHLIST` | `KTLEV,THYAO,ASELS,TUPRS,EREGL` | Seed symbols |

## Local development (without Docker)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e "packages/bist_core[dev,postgres,ai]"
pip install -r infrastructure/docker/requirements.txt

# API (SQLite works for dev; point DATABASE_URL at Postgres for the full stack)
export DEMO_MODE=true DATABASE_URL="sqlite:///./dev.db"
uvicorn app.main:app --app-dir services/api --reload

# Signal engine / notification worker (separate shells)
PYTHONPATH=services python -m signal_engine
PYTHONPATH=services python -m notification_worker

# Frontend
cd apps/web && npm install && npm run dev
```

### Database migrations

Tables are created automatically on service startup (`init_db`). TimescaleDB is
enabled by `infrastructure/migrations/0001_extensions.sql` (auto-run on first
Postgres boot). To convert the time-series tables into hypertables, run
`0002_hypertables.sql` once after startup (see the comment in that file). The
app works on plain Postgres and SQLite too.

## Testing

```bash
. .venv/bin/activate
python -m pytest tests/ -q      # 39 deterministic tests
ruff check packages services tests
```

Tests cover: price validation/ingestion, volume ratios & baselines, rolling
flow & flow acceleration, the deterministic flow score (neutral=50, bullish,
bearish, confidence downgrade), signal transitions
(strengthening/weakening/reversal), alert cooldown (incl. reversal bypass),
data-quality/freshness classification, the backtest engine's **look-ahead
prevention**, and the demo provider + pipeline.

## How the flow score works (deterministic)

The score is a **weighted sum of normalised components (each 0..1, 0.5 = neutral)**
that sum to 100, so all-neutral input yields exactly 50:

| component | weight |
|---|---|
| price momentum | 15 |
| volume | 20 |
| volume acceleration | 10 |
| price structure | 15 |
| volatility | 10 |
| technical | 15 |
| news | 15 |

Direction bands: `0–25 STRONG_NEGATIVE · 25–40 NEGATIVE · 40–60 NEUTRAL ·
60–75 POSITIVE · 75–90 STRONG_POSITIVE · 90–100 EXTREME_POSITIVE`.

**“83/100” is the strength of the current evidence, not an 83% chance of
rising.** The AI layer only explains the score; it never computes it. Every
signal persists its full `data_snapshot` (inputs, component norms, anomalies)
so it is reconstructable.

## Known limitations

- **Data is delayed (~15 min).** BIST offers no free real-time API; real-time
  use requires a licensed provider. The UI always shows `DELAYED`/`STALE`
  accordingly and never fakes `LIVE`.
- **No institutional AKD / Level-2 order book.** The free provider does not
  supply broker-attributed flow or depth. We **do not fabricate AKD**. The flow
  figures are explicitly labelled *proxies* derived from price & volume.
- **News is a compliant mock.** No site is scraped in violation of its terms; a
  licensed KAP/news provider can implement the same `NewsProvider` interface.

## Next recommended provider integration

The seams are already defined as fully-typed, intentionally-unimplemented
interfaces in `packages/bist_core/bist_core/providers/base.py`:

- `InstitutionFlowProvider` — broker-attributed net flow (AKD)
- `OrderBookProvider` — Level-2 depth
- `TradeProvider` — raw time-and-sales

A licensed provider (e.g. Matriks / Foreks) can implement these **without
changing the engines, API or UI**. Recommended first paid step once the signal
engine has proven value: add `InstitutionFlowProvider` + real-time quotes.
