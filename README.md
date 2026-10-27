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

## Weekly walk-forward research

An offline research module asks one question: **can a model rank next week's
winners better than simple baselines, consistently?**

1. Daily bars (3 years by default) are resampled into weekly bars.
2. For every stock and week, features use **only data up to that week's close**:
   1/4/12-week excess return, 4/12-week volatility, volume vs the prior 12
   weeks, distance from the 12-week high, weekly range. They are z-scored across
   stocks each week, which also strips the market-wide TL inflation drift.
3. The target is **next week's return in excess of XU100** (falls back to the
   equal-weighted universe average if XU100 is unavailable).
4. **Walk-forward:** for each week, train on everything already known, rank the
   stocks, "hold" the top N for one week, record the realised net excess return
   and the rank IC, move forward one week, repeat. All stocks are pooled: every
   chart is training data for one shared model.
5. A ridge model is compared with momentum, short-term reversal and random
   baselines, after trading costs.
6. The **last 26 weeks are a locked holdout**, opened only with
   `--segment holdout --unlock-holdout` once tuning is finished.

The verdict passes only if the model is positive after costs, beats the best
baseline, has a significant rank IC (t ≥ 2) and is positive in ≥ 60% of rolling
13-week windows. The report also lists **next week's ranking** and the model's
coefficients. Nothing is applied to live scoring or turned into orders.

```bash
pip install -e "packages/bist_core[research]"

# 1) Validate the method on data with a known answer
python -m bist_core.research --source synthetic --synthetic-momentum 0.5  # planted signal -> should PASS
python -m bist_core.research --source synthetic --synthetic-momentum 0    # pure noise    -> must FAIL

# 2) Real run (needs a running bist-data-service; run after the Friday close)
python -m bist_core.research --source bist --universe BIST30 --years 3
```

Then open `/research` in the UI (or `GET /research`). Caveats: the universe
uses today's members (survivorship bias), public data is delayed, and a
realistic weekly edge is small: an IC of 0.03–0.05 held consistently is already
good. A much higher number on real data most likely means a bug.

### Single-stock mode and other markets (e.g. SMTK on Nasdaq)

`--mode timeseries` predicts **one** stock's next week from its own history:
LONG when the model's predicted excess return is positive, otherwise FLAT. Its
baselines are buy-and-hold, 4-week momentum and a coin flip. The rank-IC t-stat
uses Bartlett's effective sample size, so overlapping (autocorrelated)
features can't inflate significance.

Be realistic about power: on synthetic data, ~3 years of weekly history detects
even a strong planted effect (correlation 0.4) only about a third of the time.
Real effects are far weaker. Prefer ranking a peer group, which pools many
stocks' history into one model.

US data comes from **Stooq** (free daily CSV, no key). The host must be allowed
by your network policy:

```bash
# Peer group: SMTK + Nasdaq small/mid-cap semiconductor & display names vs IWM
python -m bist_core.research --source stooq --universe SMTK_PEERS --benchmark IWM --cost-bps 75 --name smtk_peers
# SMTK on its own
python -m bist_core.research --source stooq --mode timeseries --symbol SMTK --benchmark IWM --cost-bps 75 --name smtk_timeseries
```

No network access to Stooq? Use local CSV files instead (e.g. Yahoo Finance
→ *Historical Data* → *Download*), one `<SYMBOL>.csv` per stock plus the
benchmark (e.g. `IWM.csv`). An `Adj Close` column is applied automatically:

```bash
python -m bist_core.research --source csv --csv-dir data --mode timeseries --symbol SMTK --benchmark IWM --cost-bps 75 --name smtk_timeseries
python -m bist_core.research --source csv --csv-dir data --benchmark IWM --cost-bps 75 --name smtk_peers  # every file = the peer group
```

Each run writes `reports/<name>.json`. `GET /research/reports` lists them, and
the `/research` page has a selector. Use a higher `--cost-bps` for thinly traded
small caps, where wide spreads dominate. The report flags very large one-day
moves, which may be genuine or unadjusted (reverse) splits.

## Automation (GitHub Actions)

Three workflows in `.github/workflows/` keep the research running without a server:

| Workflow | When | What |
|---|---|---|
| **Collect daily market data** | weekdays after the US close | Downloads daily bars for every enabled job in `automation/jobs.json` (10 years on first sight of a symbol, the last year afterwards) and merges them into CSVs on the `market-data` branch |
| **Weekly research** | Saturday morning | Runs the walk-forward research on the stored history, saves `reports/*.json` on the same branch and sends one Telegram summary per job |
| **Tests** | every push to `main` and every pull request | Lint, unit tests, TypeScript check and web build |
| **Data source probe** | pull requests touching providers/automation, or manually | Tries each source from a runner and tabulates which symbols work; commits nothing |

Collected data lives on its own branch, so the daily commits never touch the
code. When the source re-adjusts its history (e.g. after a reverse split), the
merge detects the factor from the overlapping days and rescales the older stored
rows. A Telegram warning goes out when symbols fail, data goes stale (> 5
days) or history was re-adjusted. Summaries of a FAIL verdict say explicitly
that next week's ranking is **not a signal**.

**Setup:**

1. Merge this code into the default branch. GitHub only runs scheduled
   workflows, and only shows the "Run workflow" button, for files on the
   default branch.
2. Telegram (optional, the logs always contain the text): create a bot with
   [@BotFather](https://t.me/BotFather), send it a message, then read your chat
   id from `https://api.telegram.org/bot<TOKEN>/getUpdates`. Add the repository
   secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`
   (*Settings → Secrets and variables → Actions*).
3. *Actions → Collect daily market data → Run workflow* once to start the
   history, then *Weekly research → Run workflow* to get the first report.
4. Edit `automation/jobs.json` to change universes, costs or jobs.

**Data sources.** The defaults come from the *Data source probe* workflow,
which tries each source from a GitHub runner (*Actions → Data source probe →
Run workflow* to re-check at any time). On 2026-10-26 Yahoo Finance's chart
endpoint answered for US stocks, BIST (`.IS` listings) and the XU100 index,
while Stooq returned 404. So both the US (SMTK peers vs IWM) and the BIST
(BIST30 plus other long-listed large caps, vs XU100) jobs collect from Yahoo. That endpoint is unofficial: its terms may
limit automated use and it can change, so the jobs make one light daily batch
and identify themselves honestly. Requests use explicit start/end dates
because `range=max` silently returns monthly bars, and non-daily data is
rejected. A bist-data-service job is included but disabled (needs the
`BIST_DATA_SERVICE_URL` secret).

**Which stocks are researched.** The ranking jobs only use stocks with a long
history and real trading: before each run they drop any candidate listed for
less than 8 years, with a median daily traded value (close × volume, last
~250 days) under 20M USD (US) or 500M TL (BIST, nominal: raise it with
inflation), more than 5% zero-volume days (broken data), or data lagging the
others by more than 5 days. The thresholds are `min_years`,
`min_median_value`, `max_zero_volume_share` and `max_stale_days` in
`automation/jobs.json`; every report, the status page and the Telegram summary
list how many passed and why the others dropped. The walk-forward then uses
the last 8 years of those stocks.

The same commands run anywhere:
`python -m bist_core.automation collect|research --config automation/jobs.json --store store`.

## Macro context (TCMB EVDS)

The dashboard shows a **macro context** panel (USD/TRY, EUR/TRY, …) from the
Central Bank of Türkiye's EVDS system via a `MacroDataProvider`.

- EVDS is **macro / end-of-day data (FX, rates, CPI)** — it **never** provides
  equity prices or AKD, so it is a context layer, never the market feed. Each
  series shows its own `as_of` date and a `DELAYED`/`STALE`/`DEMO` status.
- `MACRO_PROVIDER=demo` (default) works offline with deterministic values.
- For live data: register at <https://evds3.tcmb.gov.tr> → *Benim Sayfam →
  Profilim → API KEY KOPYALA*, then set `MACRO_PROVIDER=evds` and `EVDS_API_KEY`.
  The provider calls the EVDS REST API (`GET /service/evds/series=...&type=json`
  with the key in a `key` header).
- Endpoint: `GET /macro`. Track more series by editing `MACRO_SERIES`.

TCMB also publishes an official **EVDS MCP server**
(`https://mcp.tcmb.gov.tr/tcmb-mcp/evds/mcp`, OAuth) for conversational/ad-hoc
macro queries from an AI assistant — a complement to this programmatic provider,
not a backend data feed.

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
| `MACRO_PROVIDER` | `demo` | `demo` / `evds` / `none` |
| `EVDS_API_KEY` | — | TCMB EVDS API key (only for `evds`) |
| `MACRO_SERIES` | `TP.DK.USD.A,TP.DK.EUR.A` | EVDS series codes for the macro panel |

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
