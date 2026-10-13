# Quant Hub Digest Policy

**Product scope:** Launchpad + Lynch
**Last updated:** 2026-09-16

Related: [Setup Guide](SETUP_GUIDE.md) · [Launchpad Scanner](LAUNCHPAD_SCANNER.md) · [Lynch Scanner](LYNCH_SCANNER.md) · [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md) · [Runbook](RUNBOOK.md) · [NFR Code Review](nfr_code_review.md)

Recreate after SMTP edits: `./scripts/run_env.sh prod up -d --force-recreate` (dev: `./scripts/run_env.sh dev`).

## Overview

Quant Hub sends two consolidated emails. Product scans persist to Postgres with `--no-email`; digest commands read the persisted results.

| Digest | When (ET) | Command | Primary data |
|---|---|---|---|
| Daily | See `docker/crontab` (currently Mon–Fri 5:30 AM, premarket) | `quant-digest daily` | All 4 weekday Launchpad universes in crontab |
| Weekly | See `docker/crontab` (currently Saturday 8:30 AM) | `quant-digest weekly` | Lynch plus Launchpad ∩ Lynch overlap |

`docker/crontab` is the single source of truth for clock times. There is no weekday-only `sp500_index` 5:10 PM job.

## Daily Launchpad digest

The daily digest is a **premarket** brief: it runs at 5:30 AM ET, right after the weekday scans
(`most_actives` 5:00, `large_cap_growth` 5:05, `small_cap_growth` 5:10, `mid_cap_growth` 5:15 —
`docker/crontab`), and reports on the prior close's completed scan for each of those 4 universes,
before the market opens.

As of the 2026-09-16 redesign, the email covers **all 4 scanned universes** in one send (it
previously only read `most_actives`, silently discarding the other 3 universes' scans), and each
universe gets its own section:

| Section | Rule |
|---|---|
| High conviction | Launchpad Tier 1, maximum 15 names per universe |
| Watchlist | Launchpad Tier 2, maximum 10 names per universe; omit when regime is weak |
| Closest to qualifying | Top 3 Tier 3 ("near miss") names, shown **only** when a universe has zero Tier 1/2 hits, each with the factor(s) it's missing |
| Why / setup | Per-name factor highlights (e.g. squeeze compression, RVOL, MACD state) and a one-sentence setup description built from already-computed price/ATR/EMA50/support-proximity data — no new entry/stop/target trading logic |
| Changes | New and dropped names versus the prior Launchpad scan, per universe |
| Persistence | Actionable on at least 3 of the last 5 weekdays, per universe |
| Empty run | If a universe misses its scan entirely for the date, skip that universe's section (log a warning) rather than failing the whole digest. If a universe has zero Tier 1/2 hits, show its near-misses instead of blank boilerplate — a fully empty email (no hits, no near-misses, anywhere) is rare after this change but still sends successfully if it happens |

Implementation: `quant_hub/digest/analytics.py` (`build_daily_payload`, loops
`policy.DAILY_UNIVERSES`), `quant_hub/digest/humanize.py` (per-factor "why"/setup text),
`quant_hub/notify/digest_email.py` (per-universe email sections).

## Weekly Lynch digest and overlap

The weekly digest follows Saturday Launchpad coverage, Lynch coverage, and weekly analytics.

| Section | Rule |
|---|---|
| **Launchpad ∩ Lynch** | The intended combined signal: symbols actionable in both products, with both scores/tiers |
| Lynch candidates | Up to 15 passed names ranked by Lynch score |
| Regime recap | Latest available Launchpad market context |

The overlap is not optional framing. If no recent technical run or no common actionable symbols exist, the digest explicitly says so; it does not substitute a different multi-product concept.

The weekly analytics payload uses `overlap_count` and `launchpad_lynch_overlap`.

## Idempotency

- Daily: one digest per calendar day, recorded as `digest-daily-YYYY-MM-DD`.
- Weekly: one Saturday digest, recorded as `digest-weekly-YYYY-MM-DD`.

## Manual operations

```bash
docker exec quant-hub quant-digest daily
docker exec quant-hub quant-analytics weekly
docker exec quant-hub quant-digest weekly --rebuild-analytics
docker exec quant-hub quant-digest daily --no-email
```

`--rebuild-analytics` is appropriate after recovered Saturday scans or when the overlap payload must be regenerated.

## Configuration

SMTP requires values in `.env.prod` (or `.env.dev` / `.env.stage`): `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, and comma-separated `EMAIL_TO`. After editing, recreate the app container:

```bash
./scripts/run_env.sh prod up -d --force-recreate
```

See [SETUP_GUIDE.md](SETUP_GUIDE.md).
