# Quant Hub

Homelab quant scanner: named ticker universes, breakout + swing strategies, Postgres-backed results, per-ticker Yahoo cache, and a Streamlit dashboard.

## Quick start

```bash
cd /opt/stacks/quant-hub
cp .env.example .env
docker compose up -d --build
pip install -e .[dev]
quant-hub status
```

Manual scan:

```bash
quant-scan --universe sp500 --cache
quant-scan-all --cache          # all configured universes
quant-swing --universe sp500    # weekly swing setups
quant-view                      # dashboard (Postgres-backed)
```

## CLI

| Command | Purpose |
|---------|---------|
| `quant-scan` | Run breakout scan, persist to Postgres |
| `quant-scan-all` | Breakout scan across all universes in `universes.json` |
| `quant-swing` | Weekly swing setup scan (10y / 1wk OHLCV) |
| `quant-daily` | Scheduled breakout workflow (cache on, email optional) |
| `quant-universe list\|show` | Inspect universe registry |
| `quant-hub status` | DB ping, table counts, recent runs |
| `quant-hub cleanup-fixtures` | Remove test scan rows from Postgres |
| `quant-hub init-db` | Apply Postgres schema |
| `quant-view` | Streamlit dashboard |

## Architecture

- **Application:** `ScanService`, `SwingScanService`, `UniverseService`
- **Domain:** `StrategyEngine` + breakout / swing strategies
- **Infrastructure:** Postgres `ScanRepository`, `ParquetCache`, yfinance provider
- **Exports:** Per-universe paths under `data/output/{strategy}/{universe_id}/`

Universes are config-driven via `data/universes.json` + ticker files under `data/universes/`.

See `docs/USER_MANUAL.md` and `docs/RUNBOOK.md` for operator and analyst guides.
