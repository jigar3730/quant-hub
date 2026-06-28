"""Ticker deep-link navigation via query params and session state."""

from __future__ import annotations

import streamlit as st

DETAIL_TICKER_KEY = "detail_ticker"
NAV_STRATEGY_KEY = "_nav_strategy"
NAV_UNIVERSE_KEY = "_nav_universe"


def apply_pending_navigation() -> None:
    """Apply one-shot strategy/universe jumps from takeaway buttons."""
    if NAV_STRATEGY_KEY in st.session_state:
        st.session_state["sidebar_strategy"] = st.session_state.pop(NAV_STRATEGY_KEY)
    if NAV_UNIVERSE_KEY in st.session_state:
        st.session_state["sidebar_universe"] = st.session_state.pop(NAV_UNIVERSE_KEY)


def navigate_to(strategy_id: str, universe_id: str | None = None) -> None:
    st.session_state[NAV_STRATEGY_KEY] = strategy_id
    if universe_id:
        st.session_state[NAV_UNIVERSE_KEY] = universe_id
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
