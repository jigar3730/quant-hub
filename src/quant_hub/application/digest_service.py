"""Digest orchestration — readiness checks, idempotency, send."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from quant_hub.application.run_result import ServiceRunResult
from quant_hub.digest import policy as P
from quant_hub.digest.analytics import (
    build_daily_payload,
    build_weekly_payload,
    load_weekly_payload,
    save_weekly_payload,
)
from quant_hub.infrastructure.postgres.connection import ping
from quant_hub.infrastructure.postgres.repository import JobRunRepository, ScanRepository
from quant_hub.notify.digest_email import send_daily_digest, send_weekly_digest

logger = logging.getLogger(__name__)


class DigestService:
    def __init__(
        self,
        *,
        scan_repo: ScanRepository | None = None,
        job_repo: JobRunRepository | None = None,
    ) -> None:
        self.scan_repo = scan_repo or ScanRepository()
        self.job_repo = job_repo or JobRunRepository()

    def _digest_job_name(self, kind: str, key: str) -> str:
        return f"digest-{kind}-{key}"

    def _already_sent(self, job_name: str) -> bool:
        return self.job_repo.job_succeeded(job_name)

    def _check_breakout_ready(self, scan_date: date) -> None:
        run = self.scan_repo.get_latest_run(
            strategy_id="breakout",
            universe_id=P.DAILY_BREAKOUT_UNIVERSE,
            scan_date=scan_date,
        )
        if not run:
            raise RuntimeError(
                f"Breakout scan not ready for {P.DAILY_BREAKOUT_UNIVERSE} on {scan_date}"
            )
        scan_time = run.get("scan_time")
        if scan_time:
            if scan_time.tzinfo is None:
                scan_time = scan_time.replace(tzinfo=timezone.utc)
            age = datetime.now(tz=timezone.utc) - scan_time
            if age > timedelta(hours=P.DAILY_SCAN_MAX_AGE_HOURS):
                raise RuntimeError(
                    f"Breakout scan on {scan_date} is stale ({age.total_seconds() / 3600:.1f}h old)"
                )

    def _check_weekly_ready(self, lynch_date: date) -> None:
        swing = self.scan_repo.get_latest_run(
            strategy_id="swing", universe_id=P.WEEKLY_SWING_UNIVERSE
        )
        if not swing:
            raise RuntimeError(f"No swing scan for {P.WEEKLY_SWING_UNIVERSE}")
        swing_age = lynch_date - swing["scan_date"]
        if swing_age > timedelta(days=P.WEEKLY_SWING_MAX_AGE_DAYS):
            raise RuntimeError(
                f"Swing scan too old ({swing['scan_date']}); expected within {P.WEEKLY_SWING_MAX_AGE_DAYS} days"
            )

        lynch = self.scan_repo.get_latest_run(
            strategy_id="lynch",
            universe_id=P.WEEKLY_LYNCH_UNIVERSE,
            scan_date=lynch_date,
        )
        if not lynch:
            lynch_latest = self.scan_repo.get_latest_run(
                strategy_id="lynch", universe_id=P.WEEKLY_LYNCH_UNIVERSE
            )
            if not lynch_latest:
                raise RuntimeError(f"No Lynch scan for {P.WEEKLY_LYNCH_UNIVERSE}")
            lynch_age = lynch_date - lynch_latest["scan_date"]
            if lynch_age > timedelta(days=P.WEEKLY_LYNCH_MAX_AGE_DAYS):
                raise RuntimeError(
                    f"Lynch scan not ready for {lynch_date} (latest {lynch_latest['scan_date']})"
                )

    def run_analytics_weekly(self, *, lynch_date: date | None = None) -> dict:
        if not ping():
            raise RuntimeError("Database unreachable")
        lynch_date = lynch_date or date.today()
        self._check_weekly_ready(lynch_date)
        payload = build_weekly_payload(self.scan_repo, lynch_date=lynch_date)
        path = save_weekly_payload(payload, for_date=lynch_date)
        logger.info("Saved weekly analytics payload to %s", path)
        return payload

    def run_daily(
        self,
        *,
        scan_date: date | None = None,
        send_email: bool = True,
        force: bool = False,
    ) -> ServiceRunResult:
        if not ping():
            raise RuntimeError("Database unreachable")

        scan_date = scan_date or date.today()
        job_name = self._digest_job_name("daily", scan_date.isoformat())

        if not force and self._already_sent(job_name):
            logger.info("Daily digest already sent for %s — skipping", scan_date)
            return ServiceRunResult(
                dataframe=__import__("pandas").DataFrame(),
                email_requested=False,
                email_sent=False,
            )

        job_id = self.job_repo.start_job(job_name, tickers_requested=0)
        try:
            self._check_breakout_ready(scan_date)
            payload = build_daily_payload(self.scan_repo, scan_date=scan_date)

            if not payload.get("tier1") and not payload.get("tier2") and not P.DAILY_SEND_WHEN_EMPTY:
                logger.info("No signals and DAILY_SEND_WHEN_EMPTY=false — skipping email")
                email_sent = False
            elif send_email:
                email_sent = send_daily_digest(payload)
            else:
                email_sent = False

            self.job_repo.finish_job(job_id, status="success")
            logger.info("Daily digest complete for %s (email_sent=%s)", scan_date, email_sent)
            return ServiceRunResult(
                dataframe=__import__("pandas").DataFrame(),
                email_requested=send_email,
                email_sent=email_sent if send_email else False,
            )
        except Exception as exc:
            self.job_repo.finish_job(job_id, status="failed", error_message=str(exc))
            raise

    def run_weekly(
        self,
        *,
        lynch_date: date | None = None,
        send_email: bool = True,
        force: bool = False,
        use_cached_payload: bool = True,
    ) -> ServiceRunResult:
        if not ping():
            raise RuntimeError("Database unreachable")

        lynch_date = lynch_date or date.today()
        job_name = self._digest_job_name("weekly", lynch_date.isoformat())

        if not force and self._already_sent(job_name):
            logger.info("Weekly digest already sent for %s — skipping", lynch_date)
            return ServiceRunResult(
                dataframe=__import__("pandas").DataFrame(),
                email_requested=False,
                email_sent=False,
            )

        job_id = self.job_repo.start_job(job_name, tickers_requested=0)
        try:
            self._check_weekly_ready(lynch_date)
            payload = None
            if use_cached_payload:
                payload = load_weekly_payload(lynch_date)
            if payload is None:
                payload = build_weekly_payload(self.scan_repo, lynch_date=lynch_date)
                save_weekly_payload(payload, for_date=lynch_date)

            email_sent = send_weekly_digest(payload) if send_email else False
            self.job_repo.finish_job(job_id, status="success")
            logger.info("Weekly digest complete for %s (email_sent=%s)", lynch_date, email_sent)
            return ServiceRunResult(
                dataframe=__import__("pandas").DataFrame(),
                email_requested=send_email,
                email_sent=email_sent if send_email else False,
            )
        except Exception as exc:
            self.job_repo.finish_job(job_id, status="failed", error_message=str(exc))
            raise
