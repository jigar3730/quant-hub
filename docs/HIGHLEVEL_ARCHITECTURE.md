**Quant Hub is a homelab research stack**, not a trading bot. It screens lists of stocks, stores the results, and shows them in a dashboard (and email). It does **not** place trades.

It has two products:

- **Launchpad** — daily technical “coiled spring” scan (tight price action, volume dry-up, trend, MACD). Actionable means **Tier 1 or Tier 2**.
- **Lynch** — weekly Peter Lynch–style fundamental screen (growth, valuation, balance sheet). Actionable means **passed**.

The interesting combined signal is **overlap**: a ticker that is actionable in both.

---

## Big picture

Think of it as a factory line:

1. You give it **universes** (named lists of tickers, like `large_cap_growth`).
2. **Cron** (or you, via CLI) runs a scan.
3. The scan pulls prices/fundamentals from **Yahoo Finance**, using a **parquet cache** so it doesn’t re-download everything.
4. Results go into **PostgreSQL** (the source of truth).
5. The **Streamlit dashboard** and **digest emails** read those stored results.

Docker runs two containers:

- `quant-hub-db` — Postgres 16 (scan history, ML labels, job audit).
- `quant-hub` — Python app: scanners, cron, dashboard on port **5002**.

Data and logs live on the host at `/mnt/fast/quant-data/` and are mounted into the app.

---

## How a scan moves through the code

```
CLI (quant-launchpad / quant-lynch)
        ↓
Application service (orchestrates one run)
        ↓
Engine or Lynch runner (score every ticker)
        ↓
Infrastructure (Yahoo + parquet cache + Postgres)
        ↓
Dashboard / digest email / ML labels
```

- **CLI** is the button you press (`src/quant_hub/cli/`).
- **Application** is the manager: pick universe, run scan, save, maybe export (`src/quant_hub/application/`).
- **Engine / Lynch** is the scoring logic.
- **Infrastructure** talks to the outside world (Yahoo, disk cache, database).

Launchpad uses a generic `StrategyEngine` plus a strategy spec. Lynch has its own runner (`LynchScanService` → `LynchScannerRunner`).

---

## Top-level folders

| Path | Role |
|------|------|
| `src/quant_hub/` | Almost all application code |
| `data/` | Universe ticker lists and `universes.json` (in Docker this is overlaid by `/mnt/fast/quant-data/data`) |
| `docker/` | Image, cron, entrypoint |
| `docs/` | Operator manuals (scanner, ML, runbook, data model) |
| `scripts/` | One-off jobs (rescans, mega-runners research) |
| `tests/` | Unit tests |
| `docker-compose.yml` | Two-service stack |
| `pyproject.toml` | Package name, dependencies, CLI entry points |
| `.streamlit/` | Streamlit UI config |

---

## Inside `src/quant_hub/` (the important packages)

**Entry and config**

- `cli/` — commands like `quant-launchpad`, `quant-lynch`, `quant-ml`, `quant-digest`, `quant-view`, `quant-hub status`.
- `config.py` — paths (`data/`, cache, ML dirs) and scan thresholds (min price, volume, lookbacks).

**Orchestration**

- `application/` — `ScanService` (Launchpad), `LynchScanService`, universe refresh, digest, ML train/label/evaluate/export, backfill.
- `universes/` — registry and batch runs across multiple lists.

**Scoring**

- `engine/` — generic loop: load prices → filters → scores → `ScanResult`.
- `strategies/launchpad/` — Launchpad filters, tiers, aggregation.
- `factors/`, `scoring/`, `indicators.py`, `filters/` — building blocks for technical scores and eligibility.
- `lynch/` — fundamental categories, filters, metrics, explanations.
- `regime/` — market context (used by Launchpad).

**Data in / data out**

- `data/` — tickers, fundamentals, sectors, quality, provenance, news helpers.
- `infrastructure/market/` — Yahoo price/fundamental fetch.
- `infrastructure/cache/` — parquet price cache.
- `infrastructure/postgres/` — connection, `schema.sql`, repositories (`scan_runs`, `ticker_results`, jobs, ML).
- `report/` — JSON/Markdown/CSV exports.
- `notify/` — SMTP emails.
- `digest/` — daily/weekly email content rules and Command Center overlap.
- `dashboard/` — Streamlit UI (Command Center, Digest, Launchpad, Lynch).
- `history/` — ticker history projection for the UI.

**ML (Launchpad research, not live trading)**

- `ml/` — features, labels (forward returns vs SPY), train, evaluate, walk-forward.
- Models are stored and registered; they are **not** currently used to rerank live scans.

---

## Main files at the root

- **`docker-compose.yml`** — Postgres + app; dashboard `5002→5000`; DB `127.0.0.1:5433`.
- **`docker/Dockerfile`** — Python 3.12 image, installs the package, copies cron.
- **`docker/crontab`** — real schedule (weekdays Launchpad + digest; Saturday coverage, Lynch, ML labels, weekly digest). `docker/jobs.yaml` is a shorter reference and can lag crontab.
- **`data/universes.json`** — named universes pointing at files like `data/universes/large_cap_growth.txt`.
- **`src/quant_hub/infrastructure/postgres/schema.sql`** — database tables.

Postgres snapshot key is `(scan_date, strategy_id, universe_id)`. Rerunning the same product + universe + day **replaces** that day’s snapshot.

---

## Typical weekday vs Saturday

- **Mon–Fri after the close:** Launchpad on growth universes, then a daily digest email.
- **Saturday:** broader Launchpad coverage, Lynch fundamentals, attach forward-return **ML labels**, weekly analytics, weekly digest.

If you want to go deeper next, the best follow-ups are how Launchpad scoring/tiers work, how Lynch decides `passed`, or how a row gets from Yahoo into Postgres.