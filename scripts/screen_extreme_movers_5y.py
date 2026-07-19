#!/usr/bin/env python3
"""Screen tickers for |5y total return| >= 500% and write a launchpad universe file."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

CHUNK = 40
PAUSE = 1.0
THRESHOLD = 5.0  # 500% = 6x (return of +5.0) or -500% = 1/6x (return of -5/6 ≈ -0.833... wait)

# User asked "500% up or down":
#   +500% means price * 6 (return = +5.0)
#   -500% is ambiguous; commonly means loss of 5/6 ≈ -83.3% (price / 6), OR absolute move of 500%.
# We use absolute total return magnitude: |end/start - 1| >= 5.0
# That catches +500% winners and names that fell ~83%+ only if we use a lower down threshold.
# For "500% down" in trader speak people often mean 6x collapse → end/start <= 1/6.


def load_tickers(path: Path) -> list[str]:
    return sorted({line.strip().upper() for line in path.read_text().splitlines() if line.strip()})


def chunked(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def five_year_returns(tickers: list[str]) -> pd.DataFrame:
    rows: list[dict] = []
    for i, batch in enumerate(chunked(tickers, CHUNK), start=1):
        print(f"download chunk {i}/{(len(tickers) + CHUNK - 1) // CHUNK}: {len(batch)} tickers", flush=True)
        raw = yf.download(
            batch,
            period="5y",
            auto_adjust=True,
            progress=False,
            group_by="ticker",
            threads=True,
        )
        if raw.empty:
            time.sleep(PAUSE)
            continue

        if isinstance(raw.columns, pd.MultiIndex):
            for t in batch:
                if t not in raw.columns.get_level_values(0):
                    continue
                close = raw[t]["Close"].dropna()
                if len(close) < 200:
                    continue
                start = float(close.iloc[0])
                end = float(close.iloc[-1])
                if start <= 0:
                    continue
                ret = end / start - 1.0
                rows.append(
                    {
                        "ticker": t,
                        "start_close": round(start, 4),
                        "end_close": round(end, 4),
                        "return_pct": round(ret * 100, 2),
                        "multiple": round(end / start, 3),
                        "bars": len(close),
                    }
                )
        else:
            close = raw["Close"].dropna()
            if len(close) >= 200:
                start = float(close.iloc[0])
                end = float(close.iloc[-1])
                if start > 0:
                    ret = end / start - 1.0
                    rows.append(
                        {
                            "ticker": batch[0],
                            "start_close": round(start, 4),
                            "end_close": round(end, 4),
                            "return_pct": round(ret * 100, 2),
                            "multiple": round(end / start, 3),
                            "bars": len(close),
                        }
                    )
        time.sleep(PAUSE)

    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers-file", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--min-abs-return", type=float, default=THRESHOLD)
    parser.add_argument(
        "--down-multiple",
        type=float,
        default=1 / 6,
        help="Also include names with end/start <= this (default 1/6 = ~83% drawdown / 6x collapse)",
    )
    args = parser.parse_args()

    tickers = load_tickers(args.tickers_file)
    print(f"screening {len(tickers)} tickers for |return| >= {args.min_abs_return*100:.0f}% "
          f"or multiple <= {args.down_multiple}", flush=True)

    df = five_year_returns(tickers)
    if df.empty:
        print("no price data")
        return 1

    df = df.sort_values("return_pct", ascending=False)
    winners = df[df["return_pct"] >= args.min_abs_return * 100].copy()
    losers = df[df["multiple"] <= args.down_multiple].copy()
    extreme = (
        pd.concat([winners, losers])
        .drop_duplicates(subset=["ticker"])
        .sort_values("return_pct", ascending=False)
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    all_path = args.out_dir / "five_year_returns_all.csv"
    extreme_path = args.out_dir / "extreme_movers_5y.csv"
    tickers_path = args.out_dir / "extreme_movers_5y.txt"

    df.to_csv(all_path, index=False)
    extreme.to_csv(extreme_path, index=False)
    tickers_path.write_text("\n".join(extreme["ticker"].tolist()) + "\n")

    print(f"scored={len(df)} winners(+500%)={len(winners)} losers(6x down)={len(losers)} extreme={len(extreme)}")
    print(f"wrote {tickers_path}")
    print(extreme[["ticker", "return_pct", "multiple", "end_close"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
