#!/usr/bin/env python3
"""Summarize launchpad mega_runners backfill signal quality."""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict

import psycopg

URL = os.environ["DATABASE_URL"]


def main() -> None:
    with psycopg.connect(URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, job_name, status, tickers_requested, tickers_fetched,
                       tickers_failed, started_at, finished_at,
                       left(coalesce(error_message, ''), 160)
                FROM job_runs
                WHERE job_name ILIKE %s
                ORDER BY id DESC
                LIMIT 20
                """,
                ("%backfill%",),
            )
            jobs = cur.fetchall()
            print("=== RECENT BACKFILL-RELATED JOBS ===")
            if not jobs:
                cur.execute(
                    """
                    SELECT id, job_name, status, tickers_requested, tickers_fetched,
                           tickers_failed, started_at, finished_at
                    FROM job_runs
                    ORDER BY id DESC LIMIT 15
                    """
                )
                jobs = cur.fetchall()
            for r in jobs:
                print(r)

            cur.execute(
                """
                SELECT count(*), min(scan_date), max(scan_date),
                       sum(actionable_count), sum(tier1_count), sum(tier2_count), sum(tier3_count)
                FROM scan_runs
                WHERE strategy_id = 'launchpad' AND universe_id = 'mega_runners'
                """
            )
            print("\n=== SCAN_RUNS mega_runners ===")
            print(cur.fetchone())

            cur.execute(
                """
                SELECT scan_date, tier1_count, tier2_count, tier3_count,
                       filtered_count, actionable_count, id
                FROM scan_runs
                WHERE strategy_id = 'launchpad' AND universe_id = 'mega_runners'
                ORDER BY scan_date
                """
            )
            runs = cur.fetchall()
            print(f"\nrun_rows={len(runs)}")
            if not runs:
                print("No mega_runners launchpad backfill rows yet — is the job still running?")
                return

            # Tier histogram over time
            print("\n=== TIER COUNTS BY YEAR ===")
            by_year = defaultdict(lambda: Counter())
            for scan_date, t1, t2, t3, filt, act, _ in runs:
                y = scan_date.year
                by_year[y]["dates"] += 1
                by_year[y]["t1"] += t1 or 0
                by_year[y]["t2"] += t2 or 0
                by_year[y]["t3"] += t3 or 0
                by_year[y]["filt"] += filt or 0
                by_year[y]["act"] += act or 0
            for y in sorted(by_year):
                c = by_year[y]
                print(
                    f"{y}: dates={c['dates']}  Tier1={c['t1']} Tier2={c['t2']} "
                    f"Tier3={c['t3']} filtered={c['filt']} actionable={c['act']}"
                )

            # Per-ticker outcomes across all runs
            cur.execute(
                """
                SELECT tr.ticker, tr.tier, tr.eligible, tr.filter_reason,
                       tr.final_score, sr.scan_date, tr.detail
                FROM ticker_results tr
                JOIN scan_runs sr ON sr.id = tr.run_id
                WHERE sr.strategy_id = 'launchpad' AND sr.universe_id = 'mega_runners'
                ORDER BY sr.scan_date, tr.ticker
                """
            )
            rows = cur.fetchall()
            print(f"\n=== TICKER_RESULTS rows={len(rows)} ===")

            per = defaultdict(lambda: Counter())
            scores = defaultdict(list)
            actionable_events = []
            for ticker, tier, eligible, reason, score, scan_date, detail in rows:
                per[ticker]["n"] += 1
                per[ticker][str(tier or "null")] += 1
                if eligible:
                    per[ticker]["eligible"] += 1
                    if score is not None:
                        scores[ticker].append(float(score))
                else:
                    per[ticker][f"fail:{reason or 'unknown'}"] += 1
                if tier in ("Tier 1", "Tier 2") or (eligible and score is not None and score >= 55):
                    # pull factor scores from detail if present
                    factors = {}
                    if isinstance(detail, dict):
                        sc = detail.get("scores") or {}
                        for k in (
                            "squeeze_intensity",
                            "volume_vacuum_depth",
                            "trend_proximity_match",
                            "macd_zero_line",
                            "tightness_percentile",
                        ):
                            block = sc.get(k) or {}
                            if isinstance(block, dict) and "score" in block:
                                factors[k] = block["score"]
                            elif f"{k}_score" in (detail.get("summary") or {}):
                                pass
                        # also flat keys from to_row style
                        for k, v in (detail.get("summary") or {}).items():
                            if k.endswith("_score"):
                                factors[k] = v
                    actionable_events.append(
                        {
                            "date": str(scan_date),
                            "ticker": ticker,
                            "tier": tier,
                            "score": score,
                            "factors": factors,
                        }
                    )

            print("\n=== PER-TICKER SUMMARY ===")
            for ticker in sorted(per):
                c = per[ticker]
                sc = scores.get(ticker) or []
                avg = sum(sc) / len(sc) if sc else 0
                mx = max(sc) if sc else 0
                print(
                    f"{ticker}: n={c['n']} eligible={c['eligible']} "
                    f"T1={c.get('Tier 1',0)} T2={c.get('Tier 2',0)} T3={c.get('Tier 3',0)} "
                    f"avg_score={avg:.1f} max_score={mx:.1f}"
                )
                fails = {k: v for k, v in c.items() if k.startswith("fail:")}
                if fails:
                    top = sorted(fails.items(), key=lambda x: -x[1])[:3]
                    print(f"  top fails: {top}")

            print(f"\n=== ACTIONABLE / HIGH-QUALITY EVENTS (Tier1/2 or score>=55): {len(actionable_events)} ===")
            # sort by score desc then date
            actionable_events.sort(key=lambda e: (-(e["score"] or 0), e["date"]))
            for e in actionable_events[:40]:
                print(
                    f"{e['date']}  {e['ticker']:5}  {e['tier']:8}  score={e['score']}  {e['factors']}"
                )
            if len(actionable_events) > 40:
                print(f"  ... +{len(actionable_events) - 40} more")

            # Dates with any Tier 1/2
            cur.execute(
                """
                SELECT sr.scan_date, tr.ticker, tr.tier, tr.final_score
                FROM ticker_results tr
                JOIN scan_runs sr ON sr.id = tr.run_id
                WHERE sr.strategy_id = 'launchpad'
                  AND sr.universe_id = 'mega_runners'
                  AND tr.tier IN ('Tier 1', 'Tier 2')
                ORDER BY sr.scan_date, tr.ticker
                """
            )
            watch = cur.fetchall()
            print(f"\n=== ALL TIER 1/2 HITS ({len(watch)}) ===")
            for r in watch:
                print(r)


if __name__ == "__main__":
    main()
