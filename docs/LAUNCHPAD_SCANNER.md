# Launchpad Scanner

**Strategy ID:** `launchpad`  
**Product:** Quality technical scanner
**Related:** [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md) · [Lynch Scanner](LYNCH_SCANNER.md) · [Digest Policy](DIGEST_POLICY.md)
**Last updated:** 2026-07-19

## Purpose

Launchpad identifies quality technical setups in liquid stocks already showing constructive structure. It uses daily OHLCV and persists a point-in-time scan payload for dashboard review, digests, analytics, and ML.

```text
Universe → price cache/download → eligibility → factor scores → tiers
         → PostgreSQL + optional CSV/JSON/Markdown report
```

Launchpad is a stock-only product. ETF-mode universes are skipped by the all-universe and daily workflows.

## Commands

```bash
docker exec quant-hub quant-launchpad --universe mega_runners --cache --report both
docker exec quant-hub quant-launchpad-daily --universe sp500_index --no-email
docker exec quant-hub quant-launchpad-all --cache --report both
docker exec quant-hub quant-backfill launchpad --universe mega_runners --since 2021-07-29
```

## Eligibility

The scanner requires sufficient daily history, a minimum price and average volume, an aligned long-term trend, and structural proximity to the EMA50 or support. Typical failure codes include `insufficient_history`, `price_below_10`, `volume_below_min`, `macro_trend_not_aligned`, `structural_proximity`, and `no_price_data`.

## Scoring and tiers

The raw score totals 100 points:

| Factor | Max | What it measures |
|---|---:|---|
| Squeeze Intensity | 40 | Bollinger/Keltner compression |
| Tightness Percentile | 15 | Recent range tightness |
| Volume Vacuum Depth | 30 | Volume dry-up versus baseline |
| Trend & Proximity | 15 | Relative strength and proximity to support/EMA |
| MACD Zero-Line | gate | Tier 1 ignition requirement; not added to raw score |

| Tier | Rule |
|---|---|
| Tier 1 | Eligible, normalized score ≥80, and MACD zero-line gate passes |
| Tier 2 | Eligible, normalized score ≥65 |
| Tier 3 | Eligible below Tier 2 threshold |
| filtered | Failed eligibility |

Tier 1 and Tier 2 are actionable. Score thresholds and factor implementation live in `src/quant_hub/config.py`, `src/quant_hub/scoring/launchpad.py`, and `src/quant_hub/strategies/launchpad/`.

## Schedule and persistence

The authoritative schedule is `docker/crontab`: weekday `sp500_index` at 5:10 PM ET and Saturday stock-universe coverage at 1:30 AM ET. A same-day rerun replaces the run identified by `(scan_date, launchpad, universe_id)`.

`ticker_results.detail` stores eligibility, score factors, tier rationale, and `summary.final_adjusted_score`. Launchpad does not apply a market-regime multiplier (`regime_mode="none"`).

## ML

Launchpad backfill truncates daily data to each historical scan date, avoiding future price information. The ML pipeline then labels forward returns, exports features, trains models, and evaluates chronological folds. Live inference is not implemented.

Use [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md) for the complete workflow.
