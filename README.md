# Quant Hub

Homelab quant scanner: named ticker universes, breakout scoring, Postgres-backed results, per-ticker Yahoo cache, and a Streamlit dashboard.

## Quick start

```bash
cd /opt/stacks/quant-hub
cp .env.example .env
docker compose up -d --build
quant-hub status   # after pip install -e .[dev,viz]
```

Manual scan:

```bash
quant-scan --universe sp500 --cache
quant-view
```

## CLI

| Command | Purpose |
|---------|---------|
| `quant-scan` | Run breakout scan, persist to Postgres |
| `quant-daily` | Scheduled workflow (cache on, email optional) |
| `quant-universe list\|show` | Inspect universe registry |
| `quant-hub status` | DB ping, table counts, recent runs |
| `quant-hub init-db` | Apply Postgres schema |
| `quant-view` | Streamlit dashboard (reads Postgres) |

## Architecture

- **Application:** `ScanService`, `UniverseService`
- **Domain:** ported `StrategyEngine` + breakout strategy
- **Infrastructure:** Postgres `ScanRepository`, `ParquetCache`, yfinance provider

Universes are config-driven via `data/universes.json` + ticker files under `data/universes/`.

## Phase 3 extensions (pick one after 1 week of daily use)

1. Port finance-vibe as `quant-vibe` + `trade_plans` table
2. Port Lynch strategy (same repository pattern)
3. Fundamentals cache + slower fetch refactor
4. Additional universe files (growth, dividend, VBK)
5. Decommission quant-platform + finance-vibe containers

See the product build plan for acceptance criteria and gates.
