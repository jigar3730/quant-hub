# Launchpad Reversal Scanner

**Strategy ID:** `launchpad`  
**Cadence:** Daily scanner for stock universes; Saturday batch coverage/backfill for historical point-in-time runs  
**Related:** [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md) · [Breakout Scanner](BREAKOUT_SCANNER.md) · [User Manual](USER_MANUAL.md) · [Runbook](RUNBOOK.md) · [ML Ops](ML_OPS.md)

## What the scanner does

Launchpad Reversal is a daily, single-stock screening workflow built for names that are already trending upward and appear to be coiling for a breakout. The current implementation is intentionally conservative:

- It only runs against stock-mode universes. ETF-mode universes are skipped automatically.
- It uses daily OHLCV data and a point-in-time scan pipeline so historical runs can be replayed for backfills and ML-label work.
- It produces Postgres-backed results plus report artifacts for the selected universe.

The operational path is:

```text
Universe tickers → price download/cache → strategy engine → eligibility filter
  → factor scoring → tier assignment → Postgres + CSV/JSON/MD reports
```

## Entry points

| Command | Purpose |
|---------|---------|
| `quant-launchpad --universe mega_runners --cache` | Manual scan on the small tuning universe |
| `quant-launchpad --universe sp500_index --cache` | Manual single-universe scan (broad) |
| `quant-launchpad-daily --universe sp500_index --no-email` | Scheduled daily scan (cron default) |
| `quant-launchpad-all --cache --report both` | Run across all stock-mode universes |
| `quant-backfill launchpad --universe mega_runners --since 2021-07-29` | Point-in-time Saturday backfill for one universe |
| `quant-backfill launchpad --all-universes --since 2021-07-29` | Backfill every stock universe used by `quant-launchpad-all` |
| `quant-backfill coverage --strategy launchpad --universe mega_runners --since 2021-07-29` | Preview planned vs missing backfill dates |

Typical manual use from the container:

```bash
docker exec quant-hub quant-launchpad --universe mega_runners --cache --report both
docker exec quant-hub quant-launchpad-daily --universe mega_runners --no-email
docker exec quant-hub quant-launchpad-all --cache --report both
```

**ML workflow (label → export → train):** see **[Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md)**.

## Scope and eligibility

Launchpad is a single-stock strategy. It assumes the ticker already has an uptrend, enough liquidity, and enough history to evaluate structural compression. ETF-mode universes such as `sector_commodity_etfs` or `mean_reversion_core` are skipped by `quant-launchpad-all` and by the daily runner.

Eligibility is enforced in the current code via `launchpad_eligibility_detail()` and the hard gates below:

| Rule | Condition |
|------|-----------|
| Trading history | At least `LAUNCHPAD_MIN_HISTORY_DAYS` bars (currently 200) |
| Price minimum | Last close is at least `$10.00` |
| Liquidity | 30-day average volume is at least `LAUNCHPAD_MIN_AVG_VOLUME` (750,000) |
| Macro trend | Price is above the 200-day EMA |
| Structural proximity | Price within **5%** of EMA50, or within **1.0×ATR(14)** of EMA50, or within 2% of a recent support shelf |

Fail reasons include `insufficient_history`, `price_below_10`, `volume_below_min`, `macro_trend_not_aligned`, `structural_proximity`, and `no_price_data`.

## Current scoring model

The current engine uses four factor scores that normalize to a raw max of 100 points (plus a MACD gate used only for Tier 1). The implementation lives in `src/quant_hub/scoring/launchpad.py` and is wired through `src/quant_hub/strategies/launchpad/spec.py`.

| Factor | Max points | Current rule |
|--------|------------:|--------------|
| Squeeze Intensity | 40 | Bollinger/Keltner squeeze ratio; strong compression yields the full score |
| Tightness Percentile | 15 | Recent bar tightness percentile vs the prior 60 bars |
| Volume Vacuum Depth | 30 | Current volume relative to the 50-day baseline |
| Trend & Proximity | 15 | **Partial credit:** RS vs SPY (0/8) + near support (0/4/7 via % or ATR band) |
| MACD Zero-Line (gate) | 25 | Tier-1 ignition only — not added to the 100-pt raw score |

The normalized score is computed as the raw score divided by the 100-point maximum, so the final score is effectively a percent score.

## Tiering

Tiering is derived from the eligible score and the legacy MACD zero-line helper used by the tier logic:

| Tier | Rule |
|------|------|
| Tier 1 | Eligible, normalized score `>= 80`, and the MACD zero-line score is `25` |
| Tier 2 | Eligible, normalized score `>= 65` |
| Tier 3 | Eligible, normalized score below `65` |
| filtered | Failed eligibility |

## Operational workflow

### Daily scan path

The daily workflow is driven by `quant-launchpad-daily` and is intended for the weekday after-hours run. It defaults to `sp500_index` and sends no email by default when invoked with `--no-email`.

### Full coverage path

`quant-launchpad-all` is the Saturday full-coverage path. It scans every stock-mode universe that is registered for the strategy, with cache support and optional report generation.

### Backfill path

Launchpad backfills are point-in-time Saturday runs for ML and historical replay. The backfill service:

- Truncates daily OHLCV to the requested scan date before scoring.
- Replays the strategy as of that date using the same eligibility and factor logic as the live scan.
- Persists each historical run into Postgres for later dashboard and ML access.

## Schedule (America/New_York)

Authoritative cron: `docker/crontab`. Breakout/swing/Lynch scan jobs are currently commented out; Launchpad daily + Saturday full coverage remain active.

| When | Command |
|------|---------|
| Mon–Fri 5:10 PM | `quant-launchpad-daily --universe sp500_index --no-email` |
| Sat 1:30 AM | `quant-launchpad-all --cache --report both` |
| Manual backfill | `quant-backfill launchpad --universe <id> --since <date>` |

## Source code

- Strategy spec: `src/quant_hub/strategies/launchpad/spec.py`
- Scoring logic: `src/quant_hub/scoring/launchpad.py`
- Factor wiring: `src/quant_hub/factors/launchpad.py`
- Daily CLI: `src/quant_hub/cli/launchpad_daily.py`
- Batch CLI: `src/quant_hub/cli/launchpad_all.py`
- Historical backfill: `src/quant_hub/application/launchpad_backfill_service.py`
