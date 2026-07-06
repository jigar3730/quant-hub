# Mean Reversion Scanner

Daily mean-reversion rubric (v2.2) for QQQ, SPY, and sector ETFs. Produces ranked scores and trade plan cards for high-conviction setups.

## Quick start

```bash
quant-mean-reversion --universe mean_reversion_core
quant-mean-reversion --tickers QQQ SPY XLV --no-persist
quant-mean-reversion --universe mean_reversion_core --force-refresh
```

### Docker (production bind mount)

The container uses `/mnt/fast/quant-data/data` for `/app/data`, not the git repo’s `data/` tree. After adding a universe in the repo, sync to the live data volume:

```bash
cp data/universes.json /mnt/fast/quant-data/data/universes.json
cp data/universes/mean_reversion_core.txt /mnt/fast/quant-data/data/universes/
docker compose exec quant-hub quant-mean-reversion --universe mean_reversion_core --force-refresh
```

Run each `docker compose exec …` as its own command (do not paste a host-side `quant-mean-reversion` line after `exec`).

First live run should use `--force-refresh` so daily cache includes ~520+ bars for the 500 EMA (default 2y cache may only have ~277 bars).

## Universe

Default universe id: `mean_reversion_core` (QQQ, SPY, XLK, XLC, XLY, XLP, XLE, XLF, XLV, XLI, XLB, XLU).

## Data

- **Interval:** daily OHLCV
- **Lookback:** 600 calendar days (~520+ trading bars for 500 EMA)
- **Benchmark:** SPY (sector rotation RS percentile)

Outputs under `data/output/mean_reversion/{universe_id}/`:

| File | Contents |
|------|----------|
| `high_conviction.csv` | Trade plan cards (score > 71) |
| `watchlist.csv` | Marginal setups (score 62–71) |
| `full_scan.csv` | All tickers ranked by score |

## Rubric v2.2 (0–100)

Independent mean-reversion rubric on **daily close OHLCV**. Both long and short are scored; the higher side is the bias. Components sum to 100.

| Category | Max | Long | Short |
|----------|-----|------|-------|
| Macro Trend | 20 | Close > 500 EMA (10 if within 1% below) | Close < 500 EMA (10 if within 1% above) |
| Price Extension | 30 | At/below lower BB → 30; within 25% → 20; within 50% → 10 | Mirror vs upper BB |
| RSI Momentum Hook | 25 | At band zone + cross/hook from oversold (zone + direction) | At band zone + cross/hook from overbought |
| Volume Confirmation | 10 | Relative volume vs 20-day average | Same |
| Sector Rotation | 8 | RS vs SPY percentile across scan universe | Same (short favors weak RS) |
| Volatility Regime | 7 | BB width ≥ 40th percentile of 120d | Same |

## Tiers and signals

| Score | Signal | Tier | Trade plan |
|-------|--------|------|------------|
| > 71 | Strong Long / Strong Short | `HIGH_CONVICTION` | Yes |
| 62–71 | Marginal | `WATCHLIST` | No |
| < 62 | No Trade | `filtered` | No |

## Trade plan fields

High-conviction rows include: entry trigger, stop (recent swing low/high or 1.5× ATR fallback), Target 1 (BB mid), Target 2 (opposite band), options type (bull call / bear put debit spread), expiry range (45–90 DTE), suggested delta, risk notes, R:R for T1 and T2.

## Modules

| Module | Role |
|--------|------|
| `strategies/mean_reversion/scoring.py` | Rubric v2.2 |
| `strategies/mean_reversion/scanner.py` | Daily analysis + report dict |
| `strategies/mean_reversion/trade_plan.py` | Trade card builder |
| `application/mean_reversion_service.py` | Scan orchestration + Postgres |

## Postgres

Persisted with `strategy_id='mean_reversion'`. Tier mapping: `HIGH_CONVICTION` → tier1, `WATCHLIST` → tier2. Trade plans stored in `ticker_results.detail.setup_detail.trade_plan`.

## Deferred (follow-up)

- Streamlit dashboard tab
- Email digest
- `quant-mean-reversion-all` batch CLI
