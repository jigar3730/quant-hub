"""Ticker deep-link navigation via query params and session state."""

from __future__ import annotations

import streamlit as st

DETAIL_TICKER_KEY = "detail_ticker"


def ticker_link_html(ticker: str) -> str:
    """HTML link that opens the Ticker Detail view for a symbol."""
    return (
        f'<a class="ticker-link" href="?ticker={ticker}" '
        f'target="_self">{ticker}</a>'
    )


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
