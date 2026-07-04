# Mean Reversion Scanner

Daily mean-reversion rubric (v2.2) for QQQ, SPY, and sector ETFs. Produces ranked scores and trade plan cards for high-conviction setups.

## Quick start

```bash
quant-mean-reversion --universe mean_reversion_core
quant-mean-reversion --tickers QQQ SPY XLV --no-persist
quant-mean-reversion --universe mean_reversion_core --force-refresh
```

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

Both long and short are scored; the higher side is the bias.

| Category | Max | Summary |
|----------|-----|---------|
| Macro Trend | 20 | Close vs 500 EMA |
| Price Extension | 30 | Proximity to lower BB (long) or upper BB (short) |
| RSI Momentum Hook | 25 | At band + RSI hook (zone + direction) |
| Volume Confirmation | 10 | Relative volume vs 20-day average |
| Sector Rotation | 8 | RS vs SPY percentile across scan universe |
| Volatility Regime | 7 | BB width not compressed (≥ 40th percentile of 120d) |

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
