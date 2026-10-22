"""quant-research — research datasets for backtests (kept apart from production caches)."""

from __future__ import annotations

import argparse
import dataclasses
import json
from datetime import date, datetime

import pandas as pd

from quant_hub.application.research_data_service import ResearchDataService
from quant_hub.config import OUTPUT_DIR, RESEARCH_DIR
from quant_hub.logging_setup import setup_logging
from quant_hub.sector_swing import backtest as bt
from quant_hub.sector_swing import config as C


def _parse_overrides(pairs: list[str]) -> dict:
    """``--set adx_min=15`` -> {"adx_min": 15.0}, typed like the SwingParams field."""
    types = {f.name: f.type for f in dataclasses.fields(C.SwingParams)}
    out = {}
    for pair in pairs:
        key, _, raw = pair.partition("=")
        if key not in types:
            raise SystemExit(f"Unknown SwingParams field: {key}")
        kind = {"int": int, "float": float, "bool": lambda v: v.lower() in ("1", "true", "yes")}
        out[key] = kind.get(str(types[key]), str)(raw)
    return out


def _fmt(stats: dict) -> str:
    keys = ("cagr_pct", "max_drawdown_pct", "sharpe", "median_week_pct",
            "weeks_ge_2pct", "weeks_le_minus_2pct", "total_return_pct")
    return " | ".join(f"{stats.get(k, float('nan')):.2f}" for k in keys)


def _swing_backtest(args: argparse.Namespace) -> int:
    params = dataclasses.replace(C.DEFAULT_PARAMS, **_parse_overrides(args.set or []))
    cfg = bt.BacktestConfig(
        start=date.fromisoformat(args.start) if args.start else None,
        end=date.fromisoformat(args.end) if args.end else None,
        slippage_bps=args.slippage_bps,
        max_concurrent=args.max_concurrent,
        params=params,
    )
    service = ResearchDataService()
    universe = service.universe_service.resolve(universe_id=C.UNIVERSE_ID)[1]
    prices = service.cache.read_many(service.etf_tickers())
    if prices.empty:
        raise SystemExit("Research cache is empty - run: quant-research warm-history")

    signals = bt.generate_signals(prices, universe, cfg, workers=args.workers)
    result = bt.simulate(prices, signals, cfg)
    summary = bt.summarize(result)
    start, end = result.equity.index[0], result.equity.index[-1]
    baselines = {
        "SPY buy & hold": bt.buy_and_hold(prices, "SPY", start, end, cfg.initial_equity),
        "SPY when regime gate on": bt.regime_filtered_spy(prices, cfg, start, end, cfg.initial_equity),
        "Top-RS ETF, monthly": bt.top_rs_monthly(prices, universe, cfg, start, end,
                                                 cfg.initial_equity),
    }
    base_stats = {k: bt.equity_stats(v) for k, v in baselines.items()}
    yearly = bt.yearly_breakdown(result)

    label = args.label or datetime.now().strftime("%Y%m%d-%H%M%S")
    out = OUTPUT_DIR / C.STRATEGY_ID / "backtests" / label
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([t.to_row() for t in result.trades]).to_csv(out / "trades.csv", index=False)
    pd.DataFrame([dataclasses.asdict(s) for s in signals]).to_csv(out / "signals.csv", index=False)
    result.equity.rename("equity").to_csv(out / "equity.csv")
    yearly.to_csv(out / "yearly.csv", index=False)
    payload = {
        "label": label,
        "params_hash": C.params_hash(params),
        "overrides": _parse_overrides(args.set or []),
        "config": {"slippage_bps": cfg.slippage_bps, "max_concurrent": cfg.max_concurrent,
                   "window_bars": cfg.window_bars, "initial_equity": cfg.initial_equity},
        "signals": len(signals),
        "strategy": summary,
        "baselines": base_stats,
    }
    (out / "summary.json").write_text(json.dumps(payload, indent=2, default=str))

    print(f"signals={len(signals)}  -> {out}")
    print(json.dumps(summary, indent=2, default=str))
    print("\nname | CAGR% | MaxDD% | Sharpe | median wk% | wk>=+2% | wk<=-2% | total%")
    print("Swing strategy | " + _fmt(summary))
    for name, stats in base_stats.items():
        print(f"{name} | " + _fmt(stats))
    print("\n" + yearly.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Research datasets")
    sub = parser.add_subparsers(dest="command", required=True)

    warm = sub.add_parser(
        "warm-history",
        help="Download ~20y daily history for sector ETFs, benchmarks, and VIX/TNX",
    )
    warm.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignore the research cache and refetch everything",
    )

    swing = sub.add_parser(
        "swing-backtest",
        help="Point-in-time replay of the sector swing scanner with next-open fills",
    )
    swing.add_argument("--start", help="First signal date (YYYY-MM-DD)")
    swing.add_argument("--end", help="Last signal date (YYYY-MM-DD)")
    swing.add_argument("--slippage-bps", type=float, default=2.0, help="Per side (default 2)")
    swing.add_argument("--max-concurrent", type=int, default=3)
    swing.add_argument("--set", action="append", metavar="FIELD=VALUE",
                       help="Override a SwingParams field (repeatable), e.g. --set adx_min=15")
    swing.add_argument("--workers", type=int, default=3)
    swing.add_argument("--label", help="Output folder name (default: timestamp)")

    args = parser.parse_args(argv)
    setup_logging("research.log")

    if args.command == "warm-history":
        coverage = ResearchDataService().warm_etf_history(force_refresh=args.force_refresh)
        RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
        out = RESEARCH_DIR / "coverage.csv"
        coverage.to_csv(out, index=False)
        print(coverage.to_string(index=False))
        missing = coverage[coverage["bars"] == 0]["ticker"].tolist()
        print(f"\n{len(coverage)} tickers, {len(missing)} missing -> {out}")
        if missing:
            print(f"missing: {', '.join(missing)}")
            return 1
        return 0

    if args.command == "swing-backtest":
        return _swing_backtest(args)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
