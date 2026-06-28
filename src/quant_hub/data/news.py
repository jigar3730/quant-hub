"""Fetch live ticker news and market snapshot from Yahoo Finance."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import yfinance as yf

logger = logging.getLogger(__name__)


def _extract_url(content: dict) -> str | None:
    for key in ("clickThroughUrl", "canonicalUrl"):
        raw = content.get(key)
        if isinstance(raw, dict):
            url = raw.get("url")
            if url:
                return url
        elif isinstance(raw, str):
            return raw
    return None


def _format_pub_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return value


def _article_matches_ticker(article: dict, ticker: str) -> bool:
    ticker_upper = ticker.upper()
    blob = f"{article.get('title', '')} {article.get('summary', '')}".upper()
    return ticker_upper in blob or f"${ticker_upper}" in blob


def fetch_ticker_news(ticker: str, *, count: int = 8) -> list[dict]:
    """Return recent news headlines for a ticker."""
    try:
        raw = yf.Ticker(ticker).get_news(count=max(count * 2, 8), tab="news")
    except Exception:
        logger.exception("Failed to fetch news for %s", ticker)
        return []

    articles = []
    for item in raw or []:
        content = item.get("content", item)
        title = content.get("title")
        if not title:
            continue
        provider = content.get("provider") or {}
        articles.append(
            {
                "title": title,
                "summary": content.get("summary") or content.get("description") or "",
                "published": _format_pub_date(content.get("pubDate") or content.get("displayTime")),
                "publisher": provider.get("displayName", ""),
                "url": _extract_url(content),
            }
        )

    matched = [a for a in articles if _article_matches_ticker(a, ticker)]
    if matched:
        return matched[:count]
    return articles[:count]


def fetch_ticker_snapshot(ticker: str) -> dict | None:
    """Return a compact live market snapshot for a ticker."""
    try:
        fi = yf.Ticker(ticker).fast_info
        last = getattr(fi, "last_price", None)
        prev = getattr(fi, "previous_close", None) or getattr(
            fi, "regular_market_previous_close", None
        )
        if last is None:
            return None

        change_pct = None
        if prev:
            change_pct = (last - prev) / prev * 100

        year_change = getattr(fi, "year_change", None)
        return {
            "ticker": ticker,
            "price": last,
            "previous_close": prev,
            "change_pct": change_pct,
            "market_cap": getattr(fi, "market_cap", None),
            "year_change_pct": year_change * 100 if year_change is not None else None,
            "day_high": getattr(fi, "day_high", None),
            "day_low": getattr(fi, "day_low", None),
            "currency": getattr(fi, "currency", "USD"),
        }
    except Exception:
        logger.exception("Failed to fetch snapshot for %s", ticker)
        return None
