# Launchpad Reversal Scanner

**Strategy ID:** `launchpad`  
**Cadence:** Daily (`1d` bars, ~2 years history)  
**Related:** [Breakout Scanner](BREAKOUT_SCANNER.md) · [User Manual](USER_MANUAL.md) · [Runbook](RUNBOOK.md)

## Pipeline

```text
Universe tickers → download_prices() → StrategyEngine (launchpad)
  → LaunchpadEligibilityFilter (4 gates)
  → 5 factor scores (raw max 100)
  → aggregate_launchpad_ticker() → assign_tier()
  → Postgres + CSV + JSON + MD
```

## Entry points

| Command | Use |
|---------|-----|
| `quant-launchpad --universe sp500_index --cache` | Manual scan |
| `quant-launchpad-daily --universe sp500_index --no-email` | Scheduled daily |
| `quant-launchpad-all --cache --report both` | All universes |

Output: `data/output/launchpad/{universe_id}/scan_results.csv`

## Scope

Launchpad is a **single-stock** strategy: the rubric assumes individual-name MA structure and MACD pivots. **ETF-mode universes** (`eligibility_mode: "etf"`, e.g. `sector_commodity_etfs`, `mean_reversion_core`) are **skipped** — `quant-launchpad-all` filters them out and `quant-launchpad-daily` exits cleanly (rc 0) with a warning if pointed at one.

There is **no minimum-price or price-spike data-quality gate** (unlike breakout). The four rubric gates below are the only eligibility checks, plus an implicit 200-bar history requirement so SMA200 is computable.

## Layer 1 — Eligibility (hard gates)

| # | Rule | Condition |
|---|------|-----------|
| 1 | Base clearance | Price > SMA50 AND Price > SMA200 |
| 2 | Fresh trend | SMA50 > SMA50 (10 trading days ago) |
| 3 | Not extended | Price ≤ 8% above 20-day median close |
| 4 | Liquidity | 20-day avg volume ≥ 750,000 |

Fail codes: `base_not_cleared`, `trend_not_fresh`, `too_extended`, `low_liquidity`, `insufficient_history`, `no_price_data`.

## Layer 2 — Scoring (raw max 100) — the Coiled Spring engine

| Factor | Max | Scoring |
|--------|-----|---------|
| MA Tightness | 25 | Structural proximity of trend baselines. Spread ≤3% → 25 · ≤6% → 15 · else 0 |
| MACD Zero-Line | 25 | Multi-interval momentum shift. 25: MACD > signal, both > 0, **each crossed above 0 within last 5 bars** · 15: MACD > signal, both < 0 · 0: else |
| ATR Contraction | 20 | Daily candle range squeeze. `ATR(14)/ATR(50)` < 0.70 → 20 · < 0.80 → 12 · else 0 |
| Volume Dry-Up | 15 | Absolute supply exhaustion. `mean(vol 3d)/SMA(vol 50d)` ≤0.50 → 15 · ≤0.60 → 10 · else 0 |
| Swing-Low VCP | 15 | Progressive higher-low wave structure. Latest pullback depth ≤50% of prior pullback → 15 · ≤75% → 8 · else 0 (swing highs/lows over 120d) |

`normalized_score = raw / 100 × 100` (no regime multiplier).

## Layer 3 — Tiering

| Tier | Rule |
|------|------|
| Tier 1 | Normalized ≥ 80 AND MACD score = 25 |
| Tier 2 | Normalized ≥ 65 |
| Tier 3 | Eligible, normalized < 65 |
| filtered | Failed eligibility |

## Schedule (America/New_York)

| When | Command |
|------|---------|
| Mon–Fri 5:10 PM | `quant-launchpad-daily --universe sp500_index --no-email` |
| Sat 1:30 AM | `quant-launchpad-all --cache --report both` (stock-mode universes only) |

## Source code

- Spec: `src/quant_hub/strategies/launchpad/spec.py`
- Scoring: `src/quant_hub/scoring/launchpad.py`
- Factors: `src/quant_hub/factors/launchpad.py`
