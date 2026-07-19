#!/usr/bin/env python3
"""Forward returns after mega_runners launchpad high-quality hits."""

from __future__ import annotations

import os
from datetime import date

import pandas as pd
import psycopg
import yfinance as yf

URL = os.environ["DATABASE_URL"]
HORIZONS = (5, 21, 63)


def load_prices(tickers: list[str]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for t in tickers:
        raw = yf.download(t, period="6y", auto_adjust=True, progress=False)
        if raw.empty:
            continue
        df = raw.reset_index()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df.rename(columns={"Adj Close": "Close"})
        df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
        out[t] = df.sort_values("Date")
    return out


def forward_return(df: pd.DataFrame, asof: date, days: int) -> float | None:
    future = df[df["Date"].dt.date > asof]
    hist = df[df["Date"].dt.date <= asof]
    if hist.empty or len(future) < days:
        return None
    entry = float(hist["Close"].iloc[-1])
    exit_ = float(future["Close"].iloc[days - 1])
    if entry <= 0:
        return None
    return (exit_ / entry - 1.0) * 100.0


def main() -> None:
    with psycopg.connect(URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sr.scan_date, tr.ticker, tr.tier, tr.final_score, tr.detail
                FROM ticker_results tr
                JOIN scan_runs sr ON sr.id = tr.run_id
                WHERE sr.strategy_id = 'launchpad'
                  AND sr.universe_id = 'mega_runners'
                  AND tr.eligible = true
                  AND (
                    tr.tier IN ('Tier 1', 'Tier 2')
                    OR tr.final_score >= 55
                  )
                ORDER BY tr.final_score DESC NULLS LAST, sr.scan_date
                """
            )
            hits = cur.fetchall()

    if not hits:
        print("No high-quality hits found")
        return

    tickers = sorted({r[1] for r in hits})
    prices = load_prices(tickers)

    rows = []
    print("=== FORWARD RETURNS AFTER HIGH-QUALITY LAUNCHPAD HITS ===\n")
    print(
        f"{'date':10} {'ticker':5} {'tier':8} {'score':>5}  "
        + "  ".join(f"{h:>7}d" for h in HORIZONS)
        + "  factors"
    )
    for scan_date, ticker, tier, score, detail in hits:
        pdf = prices.get(ticker)
        rets = {}
        for h in HORIZONS:
            rets[h] = forward_return(pdf, scan_date, h) if pdf is not None else None
        factors = {}
        if isinstance(detail, dict):
            scores = detail.get("scores") or {}
            for k in (
                "squeeze_intensity",
                "volume_vacuum_depth",
                "tightness_percentile",
                "trend_proximity_match",
                "macd_zero_line",
            ):
                block = scores.get(k) or {}
                if isinstance(block, dict) and "score" in block:
                    factors[k[:3]] = block["score"]
        ret_str = "  ".join(
            f"{rets[h]:+6.1f}%" if rets[h] is not None else "    n/a" for h in HORIZONS
        )
        print(
            f"{scan_date} {ticker:5} {tier:8} {score:5.0f}  {ret_str}  {factors}"
        )
        rows.append(
            {
                "scan_date": scan_date,
                "ticker": ticker,
                "tier": tier,
                "score": float(score or 0),
                **{f"fwd_{h}d": rets[h] for h in HORIZONS},
            }
        )

    df = pd.DataFrame(rows)
    print("\n=== SUMMARY ===")
    print(f"hits={len(df)}")
    for h in HORIZONS:
        col = f"fwd_{h}d"
        s = df[col].dropna()
        if s.empty:
            continue
        win = (s > 0).mean() * 100
        print(
            f"{h:>3}d: n={len(s)}  win={win:.0f}%  "
            f"avg={s.mean():+.1f}%  med={s.median():+.1f}%  "
            f"best={s.max():+.1f}%  worst={s.min():+.1f}%"
        )

    # Tier 2 only
    t2 = df[df["tier"] == "Tier 2"]
    if not t2.empty:
        print("\n=== TIER 2 ONLY ===")
        for h in HORIZONS:
            col = f"fwd_{h}d"
            s = t2[col].dropna()
            if s.empty:
                continue
            print(
                f"{h:>3}d: n={len(s)}  win={(s>0).mean()*100:.0f}%  avg={s.mean():+.1f}%  med={s.median():+.1f}%"
            )

    # Deduplicate clustered PLTR weeks (keep first of consecutive)
    print("\n=== DE-CLUSTERED (drop hit if same ticker within 14d of prior) ===")
    df2 = df.sort_values(["ticker", "scan_date"]).copy()
    keep = []
    last: dict[str, date] = {}
    for _, r in df2.iterrows():
        t = r["ticker"]
        d = r["scan_date"]
        if t in last and (d - last[t]).days <= 14:
            continue
        keep.append(r)
        last[t] = d
    ddf = pd.DataFrame(keep)
    print(f"hits={len(ddf)} (from {len(df)})")
    for h in HORIZONS:
        col = f"fwd_{h}d"
        s = ddf[col].dropna()
        if s.empty:
            continue
        print(
            f"{h:>3}d: n={len(s)}  win={(s>0).mean()*100:.0f}%  "
            f"avg={s.mean():+.1f}%  med={s.median():+.1f}%"
        )
        for _, r in ddf.sort_values("scan_date").iterrows():
            if pd.isna(r[col]):
                continue
        # show each
    print("\ndeclustered detail:")
    for _, r in ddf.sort_values("scan_date").iterrows():
        bits = "  ".join(
            f"{h}d={r[f'fwd_{h}d']:+.1f}%" if pd.notna(r[f"fwd_{h}d"]) else f"{h}d=n/a"
            for h in HORIZONS
        )
        print(f"  {r['scan_date']} {r['ticker']:5} {r['tier']:8} score={r['score']:.0f}  {bits}")


if __name__ == "__main__":
    main()
