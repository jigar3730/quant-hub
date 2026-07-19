# Quant Hub Digest Policy

**Product scope:** Launchpad + Lynch
**Last updated:** 2026-07-19

Related: [Launchpad Scanner](LAUNCHPAD_SCANNER.md) · [Lynch Scanner](LYNCH_SCANNER.md) · [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md) · [Runbook](RUNBOOK.md)

## Overview

Quant Hub sends two consolidated emails. Product scans persist to Postgres with `--no-email`; digest commands read the persisted results.

| Digest | When (ET) | Command | Primary data |
|---|---|---|---|
| Daily | Mon–Fri 5:35 PM | `quant-digest daily` | Launchpad on `sp500_index` |
| Weekly | Saturday 8:00 AM | `quant-digest weekly` | Lynch plus Launchpad ∩ Lynch overlap |

## Daily Launchpad digest

The daily digest follows the 5:10 PM ET `quant-launchpad-daily --universe sp500_index --no-email` run.

| Section | Rule |
|---|---|
| High conviction | Launchpad Tier 1, maximum 15 names |
| Watchlist | Launchpad Tier 2, maximum 10 names; omit when regime is weak |
| Changes | New and dropped names versus the prior Launchpad scan |
| Persistence | Actionable on at least 3 of the last 5 weekdays |
| Empty run | Send a successful “no signals” digest |

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

SMTP requires `.env` values `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, and comma-separated `EMAIL_TO`. After editing `.env`, recreate the app container:

```bash
docker compose up -d --force-recreate quant-hub
```
