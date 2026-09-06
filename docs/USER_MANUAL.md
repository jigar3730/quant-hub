# Quant Hub User Manual

**Product:** Launchpad (quality technical scanner + ML) and Lynch (fundamental screen)
**Audience:** Analysts, traders, and operators
**Last updated:** 2026-09-06

## What Quant Hub does

Quant Hub is a research system, not an execution platform or financial advice. It stores daily technical and weekly fundamental snapshots in Postgres, presents them in Streamlit, and sends consolidated digests.

| Product | Purpose | Actionable definition |
|---|---|---|
| **Launchpad** | Quality technical setups: compression, tightness, volume dry-up, trend/proximity, and MACD ignition | Tier 1 or Tier 2 |
| **Lynch** | Peter Lynch-style fundamental candidates using growth, valuation, balance-sheet, and category checks | `passed = true` |

The primary combined research signal is **Launchpad ∩ Lynch overlap**: a ticker actionable in both products. It is an overlap, not a claim that either scanner independently predicts returns.

## Getting started

Install and start the stack with [SETUP_GUIDE.md](SETUP_GUIDE.md) (`./scripts/run_env.sh {dev|stage|prod}`). Then open the dashboard: **prod** and **dev** both default to `http://127.0.0.1:5002` on different stacks — do not run them together. Stage is port **5003**. `/mnt/fast/quant-data` is prod only. It reads Postgres; file exports are convenience copies only.

Before investigating an empty page, confirm the stack and recent runs:

```bash
cd /opt/stacks/quant-hub
./scripts/run_env.sh prod ps    # or: ./scripts/run_env.sh dev ps
docker exec quant-hub quant-hub status   # dev: quant-hub-dev
```

## Dashboard pages

The dashboard has four top-level pages:

| Page | Use it for |
|---|---|
| **Command Center** | Cross-product daily briefing, coverage, changes, and Launchpad + Lynch overlap |
| **Digest** | Preview daily Launchpad and weekly Lynch digest content from persisted data |
| **Launchpad** | Technical scan overview, full universe, ticker detail, watchlist, and comparison |
| **Lynch** | Fundamental candidates, overview, all tickers, and ticker detail |

### Command Center

Choose a scan date to see:

- Launchpad and Lynch coverage by universe.
- Actionable counts and the `overlap_count` metric.
- The `launchpad_lynch_overlap` list: tickers actionable in both products, with both scores and tiers.
- New, dropped, and persistent actionable names.
- Ticker history for a selected symbol.

Blank coverage means no run exists for that product/universe/date; it does not mean zero signals.

### Launchpad

Launchpad has **Overview**, **Full Universe**, **Ticker Detail**, **Actionable Watchlist**, and **Compare** tabs. Its technical inputs use daily OHLCV. Tier 1 requires a high score and MACD zero-line ignition; Tier 2 is the qualified watchlist. Tier 3 and filtered rows are useful for research but are not actionable.

The scanner runs only on stock-mode universes. ETF-mode universes are skipped.

### Lynch

Lynch has **Candidates**, **Overview**, **All Tickers**, and **Ticker Detail** tabs. Ticker Detail distinguishes:

- **passed** — the preset gate was met;
- **Lynch score** — percentage of quantitative checks passed;
- **categories** — `fast_grower`, `stalwart`, and/or `asset_play`;
- **data quality** — missing or failed Yahoo data is not a score of zero.

## Commands

Run commands inside the **prod** container `quant-hub`. For the practice stack use `quant-hub-dev` (see [SETUP_GUIDE.md](SETUP_GUIDE.md)). Port 5002 and `/mnt/fast/quant-data` are prod, not every environment.

```bash
docker exec quant-hub quant-launchpad --universe mega_runners --cache --report both
docker exec quant-hub quant-launchpad-daily --universe most_actives --no-email
docker exec quant-hub quant-launchpad-all --cache --report both
docker exec quant-hub quant-lynch --universe most_actives --no-email
docker exec quant-hub quant-lynch-all --no-email
docker exec quant-hub quant-hub report --strategy launchpad --universe most_actives
docker exec quant-hub quant-hub ticker history NVDA --json
```

`quant-launchpad-all` and `quant-lynch-all` cover configured stock universes. Use `quant-universe list` and `quant-universe show <id>` to inspect the registry.

Same-day reruns replace the persisted snapshot for `(scan_date, strategy_id, universe_id)`.

## Universes

The authoritative registry is `data/universes.json`. Current IDs are `large_cap_growth`, `small_cap_growth`, `mid_cap_growth`, `dividend_growers`, `fintech_growth`, `most_actives`, `sp500_index`, and `mega_runners`.

Weekday cron universes are listed in `docker/crontab` (currently the four growth lists, not a single `sp500_index` 5:10 PM job). `sp500_index` remains a named universe you can scan or refresh manually. `mega_runners` is a small curated list for Launchpad ML tuning.

On production, the container reads the bind-mounted live data at `/mnt/fast/quant-data/data/`. Copy repository changes there before running a scan.

## Digests

| Digest | Schedule (ET) | Content |
|---|---|---|
| Daily | Mon–Fri 5:40 PM ET | Launchpad Tier 1, Tier 2 when the regime permits, changes, and persistence |
| Weekly | Saturday 8:30 AM ET | Lynch candidates, with Launchpad ∩ Lynch as the intended combined signal |

Manual commands:

```bash
docker exec quant-hub quant-digest daily
docker exec quant-hub quant-analytics weekly
docker exec quant-hub quant-digest weekly --rebuild-analytics
```

See [Digest Policy](DIGEST_POLICY.md) for selection and idempotency rules.

## Schedule

`docker/crontab` is authoritative (America/New_York). Weekday Launchpad runs `most_actives`, `large_cap_growth`, `small_cap_growth`, and `mid_cap_growth` (5:10–5:25 PM), then the daily digest at 5:40 PM. Saturday coverage, Lynch, labels, analytics, and the weekly digest follow the crontab — do not copy older `sp500_index` 5:10 PM tables.

## Launchpad ML

ML is Launchpad-only. It creates point-in-time historical scans, forward-return labels, feature Parquet, LightGBM models, and walk-forward evaluation. Live scans do not use model inference yet.

Start with [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md). It documents the `mega_runners` workflow, labeling, leakage controls, training, and scaling to `sp500_index`.

## FAQ

**Why is the dashboard empty?**
No persisted run matches the selected product, universe, and date. Check `quant-hub status`, then run the relevant current CLI or wait for cron.

**Why did a score change after a rerun?**
Same-day reruns replace the earlier snapshot with the latest source data.

**Why is a Launchpad ticker filtered?**
Open Ticker Detail or inspect `filter_reason`; common causes are insufficient history, price, liquidity, trend, or structural-proximity gates.

**Why is a Lynch score blank?**
Yahoo data retrieval failed or produced insufficient data. Treat it as missing data, not zero.

**What should I prioritize weekly?**
Start with Launchpad ∩ Lynch overlap, then review each product's underlying evidence and data quality.

**Does Quant Hub trade automatically?**
No.

## Related docs

[Setup Guide](SETUP_GUIDE.md) · [Launchpad Scanner](LAUNCHPAD_SCANNER.md) · [Lynch Scanner](LYNCH_SCANNER.md) · [Digest Policy](DIGEST_POLICY.md) · [Analytics Guide](ANALYTICS_GUIDE.md) · [Data Model](DATA_MODEL.md) · [Runbook](RUNBOOK.md)
