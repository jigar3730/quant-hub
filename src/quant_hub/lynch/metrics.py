"""Fetch Peter Lynch screening metrics from yfinance."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta

import pandas as pd
import yfinance as yf

from quant_hub.config import LYNCH_FETCH_WORKERS
from quant_hub.data.fundamentals_helpers import cagr, quarterly_series
from quant_hub.data.quality import sanitize_growth_rate

logger = logging.getLogger(__name__)

PEG_SANITY_MAX = 5.0


def normalize_debt_to_equity(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    ratio = float(value)
    if ratio > 1.0:
        ratio /= 100.0
    return ratio


def normalize_dividend_yield(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    v = float(value)
    if v > 0.20:
        v /= 100.0
    return v


def compute_peg(pe: float | None, growth: float | None) -> float | None:
    if pe is None or growth is None or pd.isna(pe) or pd.isna(growth):
        return None
    if float(pe) <= 0:
        return None
    growth_pct = float(growth) * 100 if abs(float(growth)) <= 1.5 else float(growth)
    if growth_pct <= 0:
        return None
    peg = float(pe) / growth_pct
    if peg <= 0 or peg > PEG_SANITY_MAX:
        return None
    return peg


def _insider_purchases_6m(ticker: yf.Ticker) -> float | None:
    try:
        df = ticker.insider_purchases
        if df is None or df.empty:
            return None
        purchases = df.loc[df["Insider Purchases Last 6m"] == "Purchases", "Shares"]
        if purchases.empty:
            return None
        return float(purchases.iloc[0])
    except Exception:
        return None


def _shares_outstanding_change_yoy(ticker: yf.Ticker) -> float | None:
    try:
        start = (datetime.now(tz=UTC) - timedelta(days=400)).strftime("%Y-%m-%d")
        series = ticker.get_shares_full(start=start)
        if series is None or len(series) < 2:
            return None
        first = float(series.iloc[0])
        last = float(series.iloc[-1])
        if first <= 0:
            return None
        return (last - first) / first
    except Exception:
        return None


def _revenue_coefficient_of_variation(ticker: yf.Ticker) -> float | None:
    try:
        income = ticker.quarterly_income_stmt
        revenue = quarterly_series(income, "Total Revenue")
        if revenue.empty:
            revenue = quarterly_series(income, "Revenue")
        if len(revenue) < 4:
            return None
        recent = revenue.head(8).astype(float)
        mean = recent.mean()
        if mean <= 0:
            return None
        return float(recent.std() / mean)
    except Exception:
        return None


def _eps_growth_5y(ticker: yf.Ticker, info: dict) -> tuple[float | None, str]:
    try:
        income = ticker.quarterly_income_stmt
        eps = quarterly_series(income, "Diluted EPS")
        if eps.empty:
            eps = quarterly_series(income, "Basic EPS")
        eps_cagr = sanitize_growth_rate(cagr(eps, years=5.0))
        if eps_cagr is not None:
            return eps_cagr, "5-year EPS CAGR from quarterly filings"
    except Exception:
        pass
    growth = info.get("earningsGrowth")
    if growth is not None and not pd.isna(growth):
        g = sanitize_growth_rate(float(growth))
        if g is not None:
            return g, "Yahoo earningsGrowth (TTM proxy)"
    return None, ""


def _eps_growth_ttm(ticker: yf.Ticker, info: dict) -> tuple[float | None, str]:
    try:
        income = ticker.quarterly_income_stmt
        eps = quarterly_series(income, "Diluted EPS")
        if eps.empty:
            eps = quarterly_series(income, "Basic EPS")
        if len(eps) >= 8:
            recent = float(eps.iloc[-4:].sum())
            prior = float(eps.iloc[-8:-4].sum())
            if prior > 0 and recent > 0:
                yoy = sanitize_growth_rate(recent / prior - 1)
                if yoy is not None:
                    return yoy, "TTM EPS vs prior 4 quarters"
    except Exception:
        pass
    qg = info.get("earningsQuarterlyGrowth")
    if qg is not None and not pd.isna(qg):
        g = sanitize_growth_rate(float(qg))
        if g is not None:
            return g, "Yahoo earningsQuarterlyGrowth"
    return None, ""


def _pick_growth_for_peg(
    ttm: float | None,
    ttm_src: str,
    cagr5: float | None,
    cagr_src: str,
) -> tuple[float | None, str, str]:
    """Prefer recent TTM EPS trend for PEG — more aligned with current conditions."""
    if ttm is not None and ttm > 0:
        return ttm, ttm_src, "Recent TTM earnings trend (more current than 5y average)."
    if cagr5 is not None and cagr5 > 0:
        return cagr5, cagr_src, "5-year EPS compound growth (smoother, less reactive to one quarter)."
    return None, "", "No reliable positive earnings growth — PEG cannot be computed."


def fetch_lynch_metrics(ticker: str) -> dict:
    try:
        yt = yf.Ticker(ticker)
        info = yt.info or {}
    except Exception:
        logger.warning("Could not fetch Lynch metrics for %s", ticker)
        return {"ticker": ticker, "error": "fetch_failed"}

    trailing_pe = info.get("trailingPE")
    forward_pe = info.get("forwardPE")
    pe = trailing_pe if trailing_pe is not None and not pd.isna(trailing_pe) else forward_pe
    pe_source = "trailing P/E (last 12 months)" if trailing_pe else "forward P/E (estimate — less preferred)"

    eps_growth_5y, cagr_src = _eps_growth_5y(yt, info)
    eps_growth_ttm, ttm_src = _eps_growth_ttm(yt, info)
    eps_growth_for_peg, eps_growth_source, eps_growth_explanation = _pick_growth_for_peg(
        eps_growth_ttm, ttm_src, eps_growth_5y, cagr_src
    )

    peg = compute_peg(pe, eps_growth_for_peg)
    peg_source = "computed: trailing P/E ÷ earnings growth (%)"
    yahoo_peg = info.get("pegRatio")
    if peg is None and yahoo_peg is not None and not pd.isna(yahoo_peg):
        yp = float(yahoo_peg)
        if 0 < yp <= PEG_SANITY_MAX:
            peg = yp
            peg_source = "Yahoo Finance pegRatio"

    total_cash = info.get("totalCash")
    total_debt = info.get("totalDebt")
    net_cash = None
    if total_cash is not None and total_debt is not None:
        net_cash = float(total_cash) - float(total_debt)

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    shares = info.get("sharesOutstanding")
    net_cash_per_share = None
    net_cash_price_ratio = None
    if net_cash is not None and shares and float(shares) > 0 and price:
        net_cash_per_share = net_cash / float(shares)
        net_cash_price_ratio = net_cash_per_share / float(price)

    de = normalize_debt_to_equity(info.get("debtToEquity"))
    inst = info.get("heldPercentInstitutions")
    analysts = info.get("numberOfAnalystOpinions")
    insider_purchases = _insider_purchases_6m(yt)
    shares_change = _shares_outstanding_change_yoy(yt)
    revenue_cv = _revenue_coefficient_of_variation(yt)
    roe = info.get("returnOnEquity")
    div_yield = normalize_dividend_yield(info.get("dividendYield"))
    rev_growth = info.get("revenueGrowth")
    if rev_growth is not None and not pd.isna(rev_growth):
        rev_growth = sanitize_growth_rate(float(rev_growth))

    return {
        "ticker": ticker,
        "company_name": info.get("shortName") or info.get("longName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "market_cap": info.get("marketCap"),
        "price": price,
        "pe_ratio": float(pe) if pe is not None and not pd.isna(pe) else None,
        "forward_pe": float(forward_pe) if forward_pe is not None and not pd.isna(forward_pe) else None,
        "pe_source": pe_source,
        "peg_ratio": float(peg) if peg is not None and not pd.isna(peg) else None,
        "peg_source": peg_source,
        "eps_growth_5y": eps_growth_5y,
        "eps_growth_ttm": eps_growth_ttm,
        "eps_growth_for_peg": eps_growth_for_peg,
        "eps_growth_source": eps_growth_source,
        "eps_growth_explanation": eps_growth_explanation,
        "debt_to_equity": de,
        "total_cash": total_cash,
        "total_debt": total_debt,
        "net_cash": net_cash,
        "net_cash_per_share": net_cash_per_share,
        "net_cash_price_ratio": net_cash_price_ratio,
        "institutional_ownership": float(inst) if inst is not None else None,
        "analyst_count": int(analysts) if analysts is not None else None,
        "insider_purchases_6m": insider_purchases,
        "shares_outstanding_change_yoy": shares_change,
        "dividend_yield": div_yield,
        "price_to_book": info.get("priceToBook"),
        "trailing_eps": info.get("trailingEps"),
        "return_on_equity": float(roe) if roe is not None and not pd.isna(roe) else None,
        "revenue_cv": revenue_cv,
        "revenue_growth": rev_growth,
    }


def fetch_lynch_metrics_batch(
    tickers: list[str],
    *,
    max_workers: int = LYNCH_FETCH_WORKERS,
) -> list[dict]:
    if not tickers:
        return []
    if len(tickers) == 1:
        return [fetch_lynch_metrics(tickers[0])]

    workers = min(max_workers, len(tickers))
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_lynch_metrics, symbol): symbol for symbol in tickers}
        for future in as_completed(futures):
            symbol = futures[future]
            results[symbol] = future.result()
    return [results[symbol] for symbol in tickers]
