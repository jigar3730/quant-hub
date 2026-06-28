"""Shared ticker column helpers for dashboard tables."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from quant_hub.dashboard.viz.navigation import yahoo_finance_url

TICKER_LINK_HELP = "Opens the quote on Yahoo Finance."
# LinkColumn display_text only supports static text or a regex on the URL itself.
# Append #SYMBOL so the visible label shows AAPL, WFC, etc. (browsers ignore the fragment).
TICKER_LINK_DISPLAY_REGEX = r"#(.+)$"


def yahoo_ticker_link_value(ticker: str) -> str:
    symbol = ticker.strip().upper()
    return f"{yahoo_finance_url(symbol)}#{symbol}"


def with_yahoo_ticker_links(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``ticker_link`` URL column; keep ``ticker`` for selection and exports."""
    if df.empty or "ticker" not in df.columns:
        return df
    out = df.copy()
    out["ticker_link"] = (
        out["ticker"].astype(str).str.strip().str.upper().map(yahoo_ticker_link_value)
    )
    return out


def ticker_link_column_config(*, help_text: str = TICKER_LINK_HELP) -> dict:
    return {
        "ticker_link": st.column_config.LinkColumn(
            "Ticker",
            display_text=TICKER_LINK_DISPLAY_REGEX,
            help=help_text,
        ),
    }


def table_column_order(columns: list[str]) -> list[str]:
    """Show linked ticker column instead of the raw symbol column."""
    order: list[str] = []
    for column in columns:
        if column == "ticker":
            order.append("ticker_link")
        else:
            order.append(column)
    return order


def merge_column_config(extra: dict | None = None) -> dict:
    config = ticker_link_column_config()
    if extra:
        config.update(extra)
    return config
