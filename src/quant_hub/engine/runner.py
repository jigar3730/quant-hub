from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from quant_hub.data.sector import resolve_sector_etf
from quant_hub.engine.context import ScanContext
from quant_hub.engine.protocols import StrategySpec
from quant_hub.engine.types import FilterResult, ScanResult, TickerResult

logger = logging.getLogger(__name__)


class StrategyEngine:
    def __init__(
        self,
        spec: StrategySpec,
        *,
        tickers: list[str] | None = None,
        tickers_file: Path | None = None,
        dynamic_universe: bool = False,
        use_cache: bool = False,
        dry_run: bool = False,
        context: ScanContext | None = None,
    ) -> None:
        self.spec = spec
        self.tickers = tickers
        self.tickers_file = tickers_file
        self.dynamic_universe = dynamic_universe
        self.use_cache = use_cache
        self.dry_run = dry_run
        self._context = context

    def run(self) -> ScanResult:
        ctx = self._context or ScanContext.from_universe(
            tickers=self.tickers,
            tickers_file=self.tickers_file,
            dynamic_universe=self.dynamic_universe,
            use_cache=self.use_cache,
            dry_run=self.dry_run,
        )
        self._context = ctx
        logger.info(
            "Strategy %s: scanning %d tickers (regime=%s)",
            self.spec.id,
            len(ctx.universe),
            ctx.regime.label,
        )

        filter_results: dict[str, FilterResult] = {}
        eligible_tickers: list[str] = []
        ticker_results: dict[str, TickerResult] = {}

        for ticker in ctx.universe:
            df = ctx.stock_df(ticker)
            if df is None or df.empty:
                fr = FilterResult(passed=False, reason="no_price_data", checks=[])
                filter_results[ticker] = fr
                ticker_results[ticker] = TickerResult(
                    ticker=ticker,
                    eligible=False,
                    filter_reason="no_price_data",
                )
                continue

            fr = self._evaluate_filters(ctx, ticker)
            filter_results[ticker] = fr
            if fr.passed:
                sector_etf = resolve_sector_etf(ticker)
                ctx.sector_etfs[ticker] = sector_etf
                eligible_tickers.append(ticker)
                ticker_results[ticker] = TickerResult(
                    ticker=ticker,
                    eligible=True,
                    filter_reason="eligible",
                    metadata={"sector_etf": sector_etf},
                )
            else:
                ticker_results[ticker] = TickerResult(
                    ticker=ticker,
                    eligible=False,
                    filter_reason=fr.reason,
                    metadata={"sector_etf": ctx.sector_etfs.get(ticker)},
                )

        universe_factors: dict[str, dict[str, object]] = {}
        for binding in self.spec.factor_bindings:
            factor = binding.factor
            if factor.pass_kind != "universe":
                continue
            computed = factor.compute_universe(ctx, eligible_tickers)
            for ticker, result in computed.items():
                universe_factors.setdefault(ticker, {})[binding.name] = result

        for ticker in eligible_tickers:
            tr = ticker_results[ticker]
            for name, fr in universe_factors.get(ticker, {}).items():
                tr.factors[name] = fr  # type: ignore[assignment]

            for binding in self.spec.factor_bindings:
                factor = binding.factor
                if factor.pass_kind != "ticker":
                    continue
                tr.factors[binding.name] = factor.compute(ctx, ticker)

        finalized: list[TickerResult] = []
        for ticker in ctx.universe:
            tr = ticker_results[ticker]
            if tr.eligible:
                for penalty in self.spec.penalties:
                    amount = penalty.apply(ctx, tr)
                    if amount:
                        tr.penalties[penalty.name] = amount
                tr = self.spec.aggregate(tr, ctx.regime)
                tr.tier = self.spec.assign_tier(tr)
            else:
                tr.tier = "filtered"
            finalized.append(tr)

        return ScanResult(
            strategy_id=self.spec.id,
            universe=ctx.universe,
            regime=ctx.regime,
            regime_detail=ctx.regime_detail,
            tickers=finalized,
        )

    def _evaluate_filters(self, ctx: ScanContext, ticker: str) -> FilterResult:
        for filt in self.spec.filters:
            result = filt.evaluate(ctx, ticker)
            if not result.passed:
                return result
        return FilterResult(passed=True, reason="eligible", checks=[])
