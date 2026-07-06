"""Ticker deep-link navigation via query params and session state."""

from __future__ import annotations

from datetime import date

import streamlit as st

DETAIL_TICKER_KEY = "detail_ticker"
NAV_STRATEGY_KEY = "_nav_strategy"
NAV_UNIVERSE_KEY = "_nav_universe"
NAV_SCAN_DATE_KEY = "_nav_scan_date"
SHOW_GLOBAL_HISTORY_KEY = "show_global_history"
HISTORY_PAGE_OFFSET_KEY = "ticker_history_offset"


def apply_pending_navigation() -> date | None:
    """Apply one-shot strategy/universe/scan-date jumps from takeaway buttons."""
    if NAV_STRATEGY_KEY in st.session_state:
        st.session_state["sidebar_strategy"] = st.session_state.pop(NAV_STRATEGY_KEY)
    if NAV_UNIVERSE_KEY in st.session_state:
        st.session_state["sidebar_universe"] = st.session_state.pop(NAV_UNIVERSE_KEY)
    pending_date = st.session_state.pop(NAV_SCAN_DATE_KEY, None)
    if pending_date is not None:
        return date.fromisoformat(str(pending_date))
    return None


def navigate_to(strategy_id: str, universe_id: str | None = None) -> None:
    st.session_state[NAV_STRATEGY_KEY] = strategy_id
    if universe_id:
        st.session_state[NAV_UNIVERSE_KEY] = universe_id
    st.rerun()


def navigate_to_scan(
    strategy_id: str,
    universe_id: str,
    scan_date: date | str,
    *,
    detail_ticker: str | None = None,
) -> None:
    """Jump to a specific persisted scan (strategy, universe, date)."""
    st.session_state[NAV_STRATEGY_KEY] = strategy_id
    st.session_state[NAV_UNIVERSE_KEY] = universe_id
    st.session_state[NAV_SCAN_DATE_KEY] = str(scan_date)
    st.session_state[SHOW_GLOBAL_HISTORY_KEY] = False
    if detail_ticker:
        set_detail_ticker(detail_ticker)
    st.rerun()


def yahoo_finance_url(ticker: str) -> str:
    """Yahoo Finance quote URL for a US ticker symbol."""
    return f"https://finance.yahoo.com/quote/{ticker.strip().upper()}"


def ticker_link_html(ticker: str, *, internal: bool = False) -> str:
    """HTML link for a ticker symbol (Yahoo Finance by default)."""
    symbol = ticker.strip().upper()
    if internal:
        href = f"?ticker={symbol}"
        target = "_self"
        rel = ""
    else:
        href = yahoo_finance_url(symbol)
        target = "_blank"
        rel = ' rel="noopener noreferrer"'
    return (
        f'<a class="ticker-link" href="{href}" '
        f'target="{target}"{rel}>{symbol}</a>'
    )


def dashboard_ticker_link_html(ticker: str) -> str:
    """In-app link to the Ticker Detail view."""
    return ticker_link_html(ticker, internal=True)


def sync_detail_ticker() -> str | None:
    """Read ?ticker= from URL into session state; return active detail ticker."""
    if DETAIL_TICKER_KEY not in st.session_state:
        st.session_state[DETAIL_TICKER_KEY] = None

    query_ticker = st.query_params.get("ticker")
    if query_ticker:
        st.session_state[DETAIL_TICKER_KEY] = query_ticker.strip().upper()

    return st.session_state.get(DETAIL_TICKER_KEY)


def set_detail_ticker(ticker: str | None) -> None:
    if ticker:
        symbol = ticker.strip().upper()
        st.session_state[DETAIL_TICKER_KEY] = symbol
        st.query_params["ticker"] = symbol
    else:
        st.session_state[DETAIL_TICKER_KEY] = None
        if "ticker" in st.query_params:
            del st.query_params["ticker"]
