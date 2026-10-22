"""quant-research — Launchpad factor research (evidence for rubric changes)."""

from __future__ import annotations

import argparse

from quant_hub.config import ML_LABEL_CACHE_SUBDIR, ML_LABEL_CACHE_TTL_HOURS, OUTPUT_DIR
from quant_hub.infrastructure.cache.parquet_cache import ParquetCache
from quant_hub.logging_setup import setup_logging
from quant_hub.research import launchpad_factors as lf


def _launchpad_factors(args: argparse.Namespace) -> int:
    panel = lf.load_panel(args.horizon)
    if not args.include_live:
        panel = panel[panel["backfill"]]
    if panel.empty:
        raise SystemExit("No labeled Launchpad outcomes - run quant-backfill + quant-ml label first")
    cache = ParquetCache(base_dir=ML_LABEL_CACHE_SUBDIR, ttl_hours=ML_LABEL_CACHE_TTL_HOURS)
    panel = lf.add_price_benchmarks(panel, cache)
    splits = lf.default_splits(args.holdout_start)
    if args.show != "both":
        # PR-2: the holdout stays unseen until candidate rubrics are frozen.
        splits = [s for s in splits if s.name == args.show]

    columns = lf.RUBRIC_COLUMNS + lf.RAW_COLUMNS + lf.BENCHMARK_COLUMNS
    factors = lf.factor_table(panel, columns, args.horizon, splits)
    tiers = lf.tier_table(panel, args.horizon, splits)

    out = OUTPUT_DIR / "launchpad" / "research"
    out.mkdir(parents=True, exist_ok=True)
    factors.to_csv(out / f"factors_h{args.horizon}_{args.show}.csv", index=False)
    tiers.to_csv(out / f"tiers_h{args.horizon}_{args.show}.csv", index=False)
    panel.to_parquet(out / f"panel_h{args.horizon}.parquet", index=False)

    dates = panel["scan_date"]
    print(f"h={args.horizon}  rows={len(panel)}  runs={panel['run_id'].nunique()}  "
          f"dates={dates.min().date()}..{dates.max().date()}  holdout from {args.holdout_start}")
    print("\n## Factors (IC = per-run Spearman vs forward return, eligible tickers)\n")
    print(lf.as_markdown(factors))
    print("\n## Tiers (mean forward return minus universe mean)\n")
    print(lf.as_markdown(tiers))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launchpad research")
    sub = parser.add_subparsers(dest="command", required=True)
    fac = sub.add_parser("launchpad-factors", help="Factor ICs and tier spreads, design vs holdout")
    fac.add_argument("--horizon", type=int, default=20, help="Forward horizon in trading days")
    fac.add_argument("--holdout-start", default="2025-01-01",
                     help="First date of the untouched holdout period")
    fac.add_argument("--show", choices=("design", "holdout", "both"), default="design",
                     help="Which period to report (default: design only, per PR-2)")
    fac.add_argument("--include-live", action="store_true",
                     help="Also use daily live runs (default: Saturday backfill runs only)")
    args = parser.parse_args(argv)
    setup_logging("research.log")
    if args.command == "launchpad-factors":
        return _launchpad_factors(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
