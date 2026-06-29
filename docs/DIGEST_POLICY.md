# Quant Hub — Digest Email Policy

**Version:** 1.0  
**Last updated:** 2026-06-29

Related: [Analytics Guide](ANALYTICS_GUIDE.md) · [Runbook](RUNBOOK.md) · [Run Team Quickstart](RUN_TEAM_QUICKSTART.md)

---

## Overview

Quant Hub sends **two consolidated emails** instead of per-scan mail:

| Digest | When (ET) | Command |
|--------|-----------|---------|
| **Daily** | Mon–Fri 5:35 PM | `quant-digest daily` |
| **Weekly** | Sat 8:00 AM | `quant-digest weekly` |

All scheduled scans use `--no-email`. Manual scans can still send individual emails if needed.

---

## Daily digest (Mon–Fri)

**After:** `quant-daily --universe sp500 --no-email` (5:00 PM)

| Section | Rule |
|---------|------|
| **Tier 1 — High conviction** | Breakout Tier 1 only, max **15** names |
| **Tier 2 — Watchlist** | Breakout Tier 2, max **10** names; **omitted when regime = weak** |
| **New / dropped** | vs prior breakout scan date |
| **Persistent** | Actionable on ≥ **3** of last **5** weekdays |
| **Empty day** | Email still sent with “no signals” message |

### Breakout tier definitions (from scanner)

| Tier | Criteria |
|------|----------|
| **Tier 1** | normalized ≥ 80, final ≥ 70, compression ≥ 8, accumulation ≥ 8 OR rel volume ≥ 5 |
| **Tier 2** | normalized ≥ 65 |
| **Tier 3** | below 65 |

---

## Weekly digest (Saturday)

**After:** Fri swing + Sat `quant-lynch-all` (5:00 AM) + `quant-analytics weekly` (7:50 AM)

| Section | Rule |
|---------|------|
| **Triple alignment** | Breakout **Tier 1** + Swing setup (score ≥ **70** / A–B) + Lynch passed |
| **Swing highlights** | SETUP_LONG/SHORT with quality score ≥ **70**, max **15** |
| **Lynch top** | Passed names, top **15** by Lynch score |
| **Regime recap** | Breakout regime + actionable count per day this week |
| **ETF tone** | Fri `sector_commodity_etfs` breakout + swing overlap |

---

## Idempotency

- One daily digest per calendar day (`job_runs`: `digest-daily-YYYY-MM-DD`)
- One weekly digest per Saturday (`digest-weekly-YYYY-MM-DD`)
- Sat 9:00 AM retry is safe — skips if already sent

---

## Manual commands

```bash
docker exec quant-hub quant-digest daily
docker exec quant-hub quant-analytics weekly
docker exec quant-hub quant-digest weekly --rebuild-analytics
docker exec quant-hub quant-digest daily --no-email
docker exec quant-hub weekly-full-coverage   # manual full scan (all universes)
```

---

## Configuration

Thresholds: `src/quant_hub/digest/policy.py`. Rebuild container after changes.
