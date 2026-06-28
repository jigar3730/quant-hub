from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from quant_hub.application.run_result import ServiceRunResult
from quant_hub.application.universe_service import UniverseService
from quant_hub.config import SWING_MIN_BARS, scan_output_paths
from quant_hub.data.provenance import build_data_provenance
from quant_hub.data.quality import validate_ohlcv
from quant_hub.infrastructure.market.weekly_prices import download_weekly_prices
from quant_hub.infrastructure.postgres.repository import JobRunRepository, ScanRepository
from quant_hub.notify.email import send_swing_email
from quant_hub.strategies.swing.scanner import (
    SWING_FILTER_LABELS,
    SwingSetup,
    analysis_to_report,
    analyze_swing,
)

logger = logging.getLogger(__name__)


def setups_to_dataframe(setups: list[SwingSetup]) -> pd.DataFrame:
    if not setups:
        return pd.DataFrame(
            columns=["Symbol", "Setup Type", "Close", "EMA20", "EMA50", "RSI", "ATR", "Notes"]
        )
    rows = [
        {
            "Symbol": s.ticker,
            "Setup Type": s.setup_type,
            "Close": s.close,
            "EMA20": s.ema20,
            "EMA50": s.ema50,
            "RSI": s.rsi,
            "ATR": s.atr,
            "Notes": s.notes,
        }
        for s in sorted(setups, key=lambda x: x.ticker)
    ]
    return pd.DataFrame(rows)


def _data_error_report(ticker: str, reason: str) -> dict:
    label = SWING_FILTER_LABELS.get(reason, reason.replace("_", " ").title())
    return {
        "ticker": ticker,
        "eligible": False,
        "tier": "filtered",
        "sector_etf": None,
        "tier_reason": label,
        "summary": {},
        "scores": {},
        "eligibility": {"passed": False, "fail_reason": reason, "checks": []},
        "setup_detail": {"notes": label},
        "swing_checks": [],
    }


def build_swing_report(
    *,
    universe: list[str],
    tickers_report: list[dict],
    setups: list[SwingSetup],
    rejection_counts: dict[str, int],
    data_provenance: dict | None = None,
) -> dict:
    longs = [s for s in setups if s.setup_type == "SETUP_LONG"]
    shorts = [s for s in setups if s.setup_type == "SETUP_SHORT"]

    report = {
        "strategy_id": "swing",
        "scan_summary": {
            "universe_size": len(universe),
            "eligible_count": len(setups),
            "excluded_count": len(universe) - len(setups),
            "tier_counts": {
                "SETUP_LONG": len(longs),
                "SETUP_SHORT": len(shorts),
                "filtered": sum(rejection_counts.values()),
            },
            "actionable_count": len(setups),
            "filter_breakdown": rejection_counts,
            "setup_long_count": len(longs),
            "setup_short_count": len(shorts),
        },
        "market_regime": {
            "label": "weekly",
            "multiplier": 1.0,
            "interval": "1wk",
            "period": "10y",
        },
        "tickers": tickers_report,
    }
    if data_provenance:
        report["data_provenance"] = data_provenance
    return report


class SwingScanService:
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
        universe_id: str | None = "sp500",
        tickers: list[str] | None = None,
        tickers_file: Path | None = None,
        use_cache: bool = True,
        force_refresh: bool = False,
        output: Path | None = None,
        persist: bool = True,
        send_email: bool = False,
        scan_date: date | None = None,
        job_name: str | None = None,
    ) -> ServiceRunResult:
        scan_date = scan_date or date.today()
        resolved_id, universe = self.universe_service.resolve(
            universe_id=universe_id,
            tickers=tickers,
            tickers_file=tickers_file,
        )

        paths = scan_output_paths("swing", resolved_id)
        output = output or paths["csv"]

        job_id = None
        if job_name:
            job_id = self.job_repo.start_job(job_name, tickers_requested=len(universe))

        rejection_counts: dict[str, int] = {}
        setups: list[SwingSetup] = []
        ticker_reports: list[dict] = []

        try:
            logger.info(
                "Swing scan: %d tickers, 10y/1wk OHLCV (cache=%s)",
                len(universe),
                use_cache and not force_refresh,
            )
            price_map = download_weekly_prices(
                universe,
                use_cache=use_cache,
                force_refresh=force_refresh,
            )

            for ticker in universe:
                df = price_map.get(ticker)
                if df is None or df.empty:
                    reason = "no_price_data"
                    ticker_reports.append(_data_error_report(ticker, reason))
                    rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                    continue
                validation = validate_ohlcv(
                    df,
                    min_rows=SWING_MIN_BARS,
                    max_staleness_days=14,
                )
                if not validation.ok:
                    reason = validation.issues[0] if validation.issues else "invalid_ohlcv"
                    ticker_reports.append(_data_error_report(ticker, reason))
                    rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                    continue
                if len(df) < SWING_MIN_BARS:
                    reason = "insufficient_data"
                    ticker_reports.append(_data_error_report(ticker, reason))
                    rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                    continue
                try:
                    analysis = analyze_swing(df, ticker, min_bars=SWING_MIN_BARS)
                    ticker_reports.append(analysis_to_report(analysis))
                    if analysis.setup:
                        setups.append(analysis.setup)
                    elif analysis.fail_reason:
                        rejection_counts[analysis.fail_reason] = (
                            rejection_counts.get(analysis.fail_reason, 0) + 1
                        )
                except Exception:
                    logger.exception("Swing scan failed for %s", ticker)
                    reason = "scan_error"
                    ticker_reports.append(_data_error_report(ticker, reason))
                    rejection_counts[reason] = rejection_counts.get(reason, 0) + 1

            df_out = setups_to_dataframe(setups)
            output.parent.mkdir(parents=True, exist_ok=True)
            df_out.to_csv(output, index=False)
            logger.info("Wrote %d swing setups to %s", len(df_out), output)

            report = build_swing_report(
                universe=universe,
                tickers_report=ticker_reports,
                setups=setups,
                rejection_counts=rejection_counts,
                data_provenance=build_data_provenance(
                    strategy_id="swing",
                    universe_id=resolved_id,
                    scan_date=scan_date,
                    price_cache="parquet" if use_cache and not force_refresh else "live",
                    extra={"interval": "1wk", "period": "10y"},
                ),
            )

            if persist:
                run_id = self.scan_repo.upsert_scan(
                    scan_date=scan_date,
                    strategy_id="swing",
                    universe_id=resolved_id,
                    report=report,
                )
                logger.info("Persisted swing scan to Postgres run_id=%s", run_id)

            email_sent = False
            if send_email:
                email_sent = send_swing_email(report, scan_date=scan_date)
                if email_sent:
                    logger.info("Swing setups email sent")
                else:
                    logger.warning(
                        "Swing email not sent — configure SMTP_HOST, SMTP_USER, SMTP_PASSWORD, EMAIL_TO"
                    )

            if job_id is not None:
                self.job_repo.finish_job(
                    job_id,
                    status="success",
                    tickers_fetched=len(price_map),
                    tickers_failed=len(universe) - len(price_map),
                )

            logger.info(
                "Swing scan complete: %d setups (%d long, %d short)",
                len(setups),
                report["scan_summary"]["setup_long_count"],
                report["scan_summary"]["setup_short_count"],
            )
            return ServiceRunResult(
                dataframe=df_out,
                email_requested=send_email,
                email_sent=email_sent if send_email else False,
            )

        except Exception as exc:
            if job_id is not None:
                self.job_repo.finish_job(job_id, status="failed", error_message=str(exc))
            raise
