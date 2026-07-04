from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from quant_hub.application.mean_reversion_scan_core import scan_universe_daily
from quant_hub.application.run_result import ServiceRunResult
from quant_hub.application.universe_service import UniverseService
from quant_hub.config import (
    BENCHMARK_TICKER,
    DEFAULT_MEAN_REVERSION_UNIVERSE,
    MEAN_REVERSION_LOOKBACK_DAYS,
    MEAN_REVERSION_MIN_BARS,
    scan_output_paths,
)
from quant_hub.data.provenance import build_data_provenance
from quant_hub.data.quality import max_bar_date
from quant_hub.engine.context import ticker_df
from quant_hub.infrastructure.market.yfinance_prices import download_prices
from quant_hub.infrastructure.postgres.repository import JobRunRepository, ScanRepository
from quant_hub.regime.market import regime_detail

logger = logging.getLogger(__name__)


def _trade_plan_rows(reports: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for report in reports:
        plan = (report.get("setup_detail") or {}).get("trade_plan")
        if not plan:
            continue
        rows.append({
            "Symbol": plan["symbol"],
            "Setup Type": plan["setup_type"],
            "Current Price": plan["current_price"],
            "Entry Trigger": plan["entry_trigger"],
            "Stop Loss": plan["stop_loss"],
            "Target 1 (BB Mean)": plan["target_1_bb_mean"],
            "Target 2 (Opposite Band)": plan["target_2_opposite_band"],
            "Options Type": plan["options_type"],
            "Expiry Range": plan["expiry_range"],
            "Suggested Delta": plan["suggested_delta"],
            "Risk Notes": plan["risk_notes"],
            "R:R (T1)": plan["rr_t1"],
            "R:R (T2)": plan["rr_t2"],
        })
    return rows


def _watchlist_rows(reports: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for report in reports:
        wl = (report.get("setup_detail") or {}).get("watchlist")
        if wl:
            row = wl
        else:
            summary = report.get("summary") or {}
            detail = report.get("setup_detail") or {}
            row = {
                "symbol": report["ticker"],
                "setup_type": summary.get("setup_type", ""),
                "current_price": detail.get("close"),
                "score": summary.get("mean_reversion_score"),
                "status": "Watch",
                "notes": detail.get("notes", report.get("tier_reason", "")),
            }
        rows.append({
            "Symbol": row["symbol"],
            "Setup Type": row["setup_type"],
            "Current Price": row["current_price"],
            "Score": row["score"],
            "Status": row["status"],
            "Notes": row["notes"],
        })
    return rows


def _full_scan_rows(reports: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for report in sorted(
        reports,
        key=lambda r: (r.get("summary") or {}).get("mean_reversion_score") or 0,
        reverse=True,
    ):
        summary = report.get("summary") or {}
        detail = report.get("setup_detail") or {}
        rows.append({
            "Symbol": report["ticker"],
            "Tier": report.get("tier"),
            "Setup Type": summary.get("setup_type", ""),
            "Score": summary.get("mean_reversion_score"),
            "Signal": summary.get("signal", ""),
            "Long Score": summary.get("long_score"),
            "Short Score": summary.get("short_score"),
            "Close": detail.get("close"),
            "RSI": detail.get("rsi"),
            "Notes": detail.get("notes", report.get("tier_reason", "")),
        })
    return rows


def build_mean_reversion_report(
    *,
    universe: list[str],
    tickers_report: list[dict],
    high_conviction: list[dict],
    watchlist: list[dict],
    rejection_counts: dict[str, int],
    regime_detail_dict: dict,
    data_provenance: dict | None = None,
) -> dict:
    report = {
        "strategy_id": "mean_reversion",
        "scan_summary": {
            "universe_size": len(universe),
            "eligible_count": len(high_conviction) + len(watchlist),
            "excluded_count": len(universe) - len(high_conviction) - len(watchlist),
            "tier_counts": {
                "HIGH_CONVICTION": len(high_conviction),
                "WATCHLIST": len(watchlist),
                "filtered": len(universe) - len(high_conviction) - len(watchlist),
            },
            "actionable_count": len(high_conviction),
            "filter_breakdown": rejection_counts,
            "high_conviction_count": len(high_conviction),
            "watchlist_count": len(watchlist),
        },
        "market_regime": regime_detail_dict,
        "tickers": tickers_report,
    }
    if data_provenance:
        report["data_provenance"] = data_provenance
    return report


class MeanReversionScanService:
    def __init__(
        self,
        *,
        universe_service: UniverseService | None = None,
        scan_repo: ScanRepository | None = None,
        job_repo: JobRunRepository | None = None,
    ) -> None:
        self.universe_service = universe_service or UniverseService()
        self.scan_repo = scan_repo or ScanRepository()
        self.job_repo = job_repo or JobRunRepository()

    def run(
        self,
        *,
        universe_id: str | None = DEFAULT_MEAN_REVERSION_UNIVERSE,
        tickers: list[str] | None = None,
        tickers_file: Path | None = None,
        use_cache: bool = True,
        force_refresh: bool = False,
        output: Path | None = None,
        persist: bool = True,
        scan_date: date | None = None,
        job_name: str | None = None,
    ) -> ServiceRunResult:
        scan_date = scan_date or date.today()
        resolved_id, universe = self.universe_service.resolve(
            universe_id=universe_id,
            tickers=tickers,
            tickers_file=tickers_file,
        )

        paths = scan_output_paths("mean_reversion", resolved_id)
        output = output or paths["csv"]

        job_id = None
        if job_name:
            job_id = self.job_repo.start_job(job_name, tickers_requested=len(universe))

        try:
            download_tickers = sorted(set(universe) | {BENCHMARK_TICKER})
            logger.info(
                "Mean reversion scan: %d tickers, daily OHLCV %dd lookback (cache=%s)",
                len(universe),
                MEAN_REVERSION_LOOKBACK_DAYS,
                use_cache and not force_refresh,
            )
            prices = download_prices(
                download_tickers,
                use_cache=use_cache and not force_refresh,
                lookback_days=MEAN_REVERSION_LOOKBACK_DAYS,
            )
            price_map = {
                ticker: ticker_df(prices, ticker)
                for ticker in universe
                if ticker_df(prices, ticker) is not None
            }
            spy_df = ticker_df(prices, BENCHMARK_TICKER)
            regime_info = regime_detail(spy_df) if spy_df is not None and not spy_df.empty else {
                "label": "unknown",
                "multiplier": 1.0,
            }

            high_conviction, watchlist, all_reports, rejection_counts = scan_universe_daily(
                universe,
                price_map,
                spy_df,
                min_bars=MEAN_REVERSION_MIN_BARS,
                scan_date=scan_date,
            )

            hc_df = pd.DataFrame(_trade_plan_rows(high_conviction))
            wl_df = pd.DataFrame(_watchlist_rows(watchlist))
            full_df = pd.DataFrame(_full_scan_rows(all_reports))

            output.parent.mkdir(parents=True, exist_ok=True)
            hc_df.to_csv(output, index=False)
            paths["watchlist_csv"].parent.mkdir(parents=True, exist_ok=True)
            wl_df.to_csv(paths["watchlist_csv"], index=False)
            full_df.to_csv(paths["full_scan_csv"], index=False)
            logger.info(
                "Wrote mean reversion outputs: %d high conviction, %d watchlist to %s",
                len(hc_df),
                len(wl_df),
                output.parent,
            )

            report = build_mean_reversion_report(
                universe=universe,
                tickers_report=all_reports,
                high_conviction=high_conviction,
                watchlist=watchlist,
                rejection_counts=rejection_counts,
                regime_detail_dict=regime_info,
                data_provenance=build_data_provenance(
                    strategy_id="mean_reversion",
                    universe_id=resolved_id,
                    scan_date=scan_date,
                    price_cache="parquet" if use_cache and not force_refresh else "live",
                    as_of_price=(
                        str(max_bar_date(spy_df)) if spy_df is not None else None
                    ),
                    extra={
                        "interval": "1d",
                        "lookback_days": MEAN_REVERSION_LOOKBACK_DAYS,
                    },
                ),
            )

            if persist:
                run_id = self.scan_repo.upsert_scan(
                    scan_date=scan_date,
                    strategy_id="mean_reversion",
                    universe_id=resolved_id,
                    report=report,
                )
                logger.info("Persisted mean reversion scan to Postgres run_id=%s", run_id)

            if job_id is not None:
                self.job_repo.finish_job(
                    job_id,
                    status="success",
                    tickers_fetched=len(price_map),
                    tickers_failed=len(universe) - len(price_map),
                )

            logger.info(
                "Mean reversion scan complete: %d high conviction, %d watchlist",
                len(high_conviction),
                len(watchlist),
            )
            return ServiceRunResult(dataframe=hc_df)

        except Exception as exc:
            if job_id is not None:
                self.job_repo.finish_job(job_id, status="failed", error_message=str(exc))
            raise
