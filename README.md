# Quant Hub

Homelab quant scanner: named ticker universes, breakout + swing + Lynch strategies, Postgres-backed results, per-ticker Yahoo cache, and a Streamlit dashboard.

## Quick start

```bash
cd /opt/stacks/quant-hub
cp .env.example .env
docker compose up -d --build
pip install -e .[dev,viz]
quant-hub status
```

Manual scan:

```bash
quant-scan --universe sp500 --cache
quant-scan-all --cache          # all configured universes
quant-swing --universe sp500    # weekly swing setups (full-universe detail + quality score)
quant-lynch --universe sp500    # Peter Lynch fundamental screen
quant-view                      # dashboard (Postgres-backed)
```

## CLI

| Command | Purpose |
|---------|---------|
| `quant-scan` | Run breakout scan, persist to Postgres |
| `quant-scan-all` | Breakout scan across all universes in `universes.json` |
| `quant-swing` | Weekly swing scan (10y / 1wk OHLCV); setup gate + 0–100 quality score |
| `quant-lynch` | Peter Lynch fundamental screen with fetch-quality tracking |
| `quant-daily` | Scheduled breakout workflow (cache on, email optional) |
| `quant-universe list\|show` | Inspect universe registry |
| `quant-hub status` | DB ping, table counts, recent runs |
| `quant-hub cleanup-fixtures` | Remove test scan rows from Postgres |
| `quant-hub init-db` | Apply Postgres schema |
| `quant-view` | Streamlit dashboard |

## Dashboard highlights

- **Breakout:** takeaway banner, near-miss panel, full-universe table with Yahoo ticker links, actionable signal tooltips
- **Swing:** weekly setups ranked by **quality score** (partial rule credit − penalties), grade A–D, full-universe indicators for every ticker
- **Lynch:** candidates-first layout, data-fetch quality banner, plain-English check explanations

Ticker columns link to **Yahoo Finance** quotes. Use **Ticker Detail** / row selection for in-app scan profiles.

## Architecture

- **Application:** `ScanService`, `SwingScanService`, `LynchScanService`, `UniverseService`
- **Domain:** `StrategyEngine` + breakout / swing / Lynch strategies
- **Infrastructure:** Postgres `ScanRepository`, `ParquetCache`, yfinance provider
- **Exports:** Per-universe paths under `data/output/{strategy}/{universe_id}/`

Universes are config-driven via `data/universes.json` + ticker files under `data/universes/`.

**Operator scripts:** `scripts/full-rescan.sh` — truncate Postgres scan history and re-run breakout, swing, and Lynch for all universes.

See `docs/USER_MANUAL.md` and `docs/RUNBOOK.md` for operator and analyst guides.
