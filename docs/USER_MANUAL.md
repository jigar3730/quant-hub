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

### Sector ETF swing

A separate scanner looks for **short swing trades (about 3–10 trading days)** in a list of sector ETFs (`sector_etfs`) that are already beating SPY, have dipped, and are turning back up. It runs before the open each weekday, so every price is the previous close. Each plan comes with a stop chosen *before* entry. It is a research tool: nothing places orders, and no return is promised.

View it on the React frontend's **Sector Swing** page (`/swing`; dev stack today) — there is no Streamlit tab, since Streamlit is being retired. The page has a **How to read this page** panel (open on your first visit, reopen any time) with the same content as below. Without the UI, read `data/output/sector_etf_swing/sector_etfs/summary.md` or `quant-hub status`.

**How to read it, in four steps**

1. **Read the coloured headline.** It says in one sentence what today means: trade plans ready, leaders being watched, or nothing to do. "Nothing to do" is a normal and frequent answer.
2. **Check the market gate.** If SPY is below its 50- or 200-day average the bar is red and *no* plans are issued, however good an ETF looks.
3. **If there is a trade plan**, read the **In plain English** line first, for example: *"This plan would buy about 108 shares of XLK near 137.62 (no higher than 138.47), and exit if the price falls to 133.45 — roughly $450 at risk. First target: 145.9, twice the amount risked."* Then follow the checklist on the card:
   - *Before the open:* skip the trade if the open is above the **chase limit** (too far from the plan) or at/below the **stop** (the idea is already wrong), and confirm the levels against a live quote.
   - *After entering:* sell half at the **2R target**, trail the rest (exit on a daily close below the 10-day average), and exit at the close if it has not gained 1× the risk within 10 trading days.
4. **Use the ranked table to see why not.** All 16 ETFs are listed against SPY. Seven chips (R1–R7) show the checks in order — green passed, red failed, grey not checked because an earlier one failed. Hover a chip for the value and threshold.

**Labels:** *Trigger* (Tier 1) is a full plan and the only actionable tier. *Watch* (Tier 2) is a leader that is dipping but has not turned up yet. *Extended* (Tier 3) is a leader that has not pulled back, so buying would be chasing. *Filtered* did not qualify; the Outcome column says why.

**Sizing:** enter your own equity and risk % on the page (stored in your browser only). Share counts are recomputed from them; the scanner's own share count uses a placeholder $50,000 / 1%, and a position is capped at 30% of equity.

See [SECTOR_SWING_SCANNER.md](SECTOR_SWING_SCANNER.md) for the exact rules.

## Commands

Run commands inside the **prod** container `quant-hub`. For the practice stack use `quant-hub-dev` (see [SETUP_GUIDE.md](SETUP_GUIDE.md)). Port 5002 and `/mnt/fast/quant-data` are prod, not every environment.

```bash
docker exec quant-hub quant-launchpad --universe mega_runners --cache --report both
docker exec quant-hub quant-launchpad-daily --universe most_actives --no-email
docker exec quant-hub quant-launchpad-all --cache --report both
docker exec quant-hub quant-lynch --universe most_actives --no-email
docker exec quant-hub quant-lynch-all --no-email
docker exec quant-hub quant-sector-swing --force-refresh
docker exec quant-hub quant-hub report --strategy launchpad --universe most_actives
docker exec quant-hub quant-hub ticker history NVDA --json
```

`quant-launchpad-all` and `quant-lynch-all` cover configured stock universes. Use `quant-universe list` and `quant-universe show <id>` to inspect the registry.

Same-day reruns replace the persisted snapshot for `(scan_date, strategy_id, universe_id)`.

## Universes

The authoritative registry is `data/universes.json`. Current IDs are `large_cap_growth`, `small_cap_growth`, `mid_cap_growth`, `dividend_growers`, `most_actives`, `sp500_index`, and `mega_runners`.

Weekday cron universes are listed in `docker/crontab` (currently the four growth lists, not a single `sp500_index` 5:10 PM job). `sp500_index` remains a named universe you can scan or refresh manually. `mega_runners` is a small curated list for Launchpad ML tuning.

On production, the container reads the bind-mounted live data at `/mnt/fast/quant-data/data/`. Copy repository changes there before running a scan.

## Digests

| Digest | Schedule (ET) | Content |
|---|---|---|
| Daily | Mon–Fri 5:30 AM ET (premarket) | All 4 Launchpad universes: Tier 1, Tier 2 when the regime permits, near-misses when a universe has neither, changes, and persistence |
| Weekly | Saturday 8:30 AM ET | Lynch candidates, with Launchpad ∩ Lynch as the intended combined signal |

Manual commands:

```bash
docker exec quant-hub quant-digest daily
docker exec quant-hub quant-analytics weekly
docker exec quant-hub quant-digest weekly --rebuild-analytics
```

See [Digest Policy](DIGEST_POLICY.md) for selection and idempotency rules.

## Schedule

`docker/crontab` is authoritative (America/New_York). Weekday Launchpad runs `most_actives`, `large_cap_growth`, `small_cap_growth`, and `mid_cap_growth` (5:00–5:15 AM), the sector-ETF swing scan at 5:20 AM, then the daily digest at 5:30 AM — all premarket, before the open. Saturday coverage, Lynch, labels, analytics, and the weekly digest follow the crontab — do not copy older `sp500_index` 5:10 PM tables.

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
