"""Short-TTL caching for the hottest Postgres reads.

Streamlit re-runs the whole script on every widget interaction, so without
caching, each rerun re-issues the same list_runs/load_report queries even
when nothing in Postgres has changed since the last rerun. A short TTL keeps
a cron-landed scan visible within one normal browsing session while cutting
the redundant reads a single session otherwise repeats on every click.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import streamlit as st

from quant_hub.infrastructure.postgres.repository import ScanRepository

_TTL = 20  # seconds — well under the gap between cron-scheduled scans


@st.cache_data(ttl=_TTL, show_spinner=False)
def cached_list_runs(
    strategy_id: str, limit: int, exclude_fixtures: bool
) -> list[dict[str, Any]]:
    return ScanRepository().list_runs(
        strategy_id=strategy_id, limit=limit, exclude_fixtures=exclude_fixtures
    )


@st.cache_data(ttl=_TTL, show_spinner=False)
def cached_list_scan_dates(limit: int, exclude_fixtures: bool) -> list[date]:
    return ScanRepository().list_scan_dates(limit=limit, exclude_fixtures=exclude_fixtures)


@st.cache_data(ttl=_TTL, show_spinner=False)
def cached_load_report(
    strategy_id: str,
    universe_id: str | None,
    scan_date: date | None,
    exclude_fixtures: bool,
) -> dict[str, Any] | None:
    return ScanRepository().load_report(
        strategy_id=strategy_id,
        universe_id=universe_id,
        scan_date=scan_date,
        exclude_fixtures=exclude_fixtures,
    )


@st.cache_data(ttl=_TTL, show_spinner=False)
def cached_table_counts() -> dict[str, int]:
    return ScanRepository().table_counts()


@st.cache_data(ttl=_TTL, show_spinner=False)
def cached_command_center_payload(scan_date: date) -> dict[str, Any]:
    from quant_hub.digest.command_center import build_command_center_payload

    return build_command_center_payload(ScanRepository(), scan_date=scan_date)
