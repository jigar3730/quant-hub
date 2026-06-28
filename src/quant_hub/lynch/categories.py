"""Lynch stock category presets (Fast Grower, Stalwart, Asset Play)."""

from __future__ import annotations

from quant_hub.lynch import config as cfg
from quant_hub.lynch.filters import _check


def classify_fast_grower(metrics: dict) -> tuple[bool, list[dict]]:
    checks: list[dict] = []
    mcap = metrics.get("market_cap")
    mcap_ok = mcap is not None and mcap < cfg.FAST_GROWER_MCAP_MAX
    checks.append(
        _check(
            "market_cap",
            mcap_ok,
            value=mcap,
            threshold=f"< ${cfg.FAST_GROWER_MCAP_MAX / 1e9:.0f}B",
        )
    )

    growth = metrics.get("eps_growth_for_peg") or metrics.get("eps_growth_5y")
    growth_ok = growth is not None and float(growth) >= cfg.FAST_GROWER_EPS_GROWTH_MIN
    checks.append(
        _check(
            "eps_growth",
            growth_ok,
            value=growth,
            threshold=f">= {cfg.FAST_GROWER_EPS_GROWTH_MIN:.0%}",
        )
    )

    peg = metrics.get("peg_ratio")
    peg_ok = peg is not None and peg < cfg.FAST_GROWER_PEG_MAX
    checks.append(_check("peg_ratio", peg_ok, value=peg, threshold=f"< {cfg.FAST_GROWER_PEG_MAX}"))

    de = metrics.get("debt_to_equity")
    de_ok = de is not None and de < cfg.FAST_GROWER_DE_MAX
    checks.append(
        _check(
            "debt_to_equity",
            de_ok,
            value=de,
            threshold=f"< {cfg.FAST_GROWER_DE_MAX:.2f} (D/E ratio)",
        )
    )

    return all(c["passed"] for c in checks), checks


def classify_stalwart(metrics: dict) -> tuple[bool, list[dict]]:
    checks: list[dict] = []
    mcap = metrics.get("market_cap")
    mcap_ok = mcap is not None and mcap > cfg.STALWART_MCAP_MIN
    checks.append(
        _check(
            "market_cap",
            mcap_ok,
            value=mcap,
            threshold=f"> ${cfg.STALWART_MCAP_MIN / 1e9:.0f}B",
        )
    )

    pe = metrics.get("pe_ratio")
    pe_ok = pe is not None and pe < cfg.STALWART_PE_MAX
    checks.append(_check("pe_ratio", pe_ok, value=pe, threshold=f"< {cfg.STALWART_PE_MAX}"))

    growth = metrics.get("eps_growth_for_peg") or metrics.get("eps_growth_5y")
    growth_ok = (
        growth is not None
        and cfg.STALWART_EPS_GROWTH_MIN <= float(growth) <= cfg.STALWART_EPS_GROWTH_MAX
    )
    checks.append(
        _check(
            "eps_growth",
            growth_ok,
            value=growth,
            threshold=f"{cfg.STALWART_EPS_GROWTH_MIN:.0%} – {cfg.STALWART_EPS_GROWTH_MAX:.0%}",
        )
    )

    div = metrics.get("dividend_yield")
    div_ok = div is not None and float(div) >= cfg.STALWART_DIVIDEND_YIELD_MIN
    checks.append(
        _check(
            "dividend_yield",
            div_ok,
            value=div,
            threshold=f">= {cfg.STALWART_DIVIDEND_YIELD_MIN:.1%}",
        )
    )

    return all(c["passed"] for c in checks), checks


def classify_asset_play(metrics: dict) -> tuple[bool, list[dict]]:
    checks: list[dict] = []
    pb = metrics.get("price_to_book")
    pb_ok = pb is not None and pb < cfg.ASSET_PLAY_PB_MAX
    checks.append(
        _check("price_to_book", pb_ok, value=pb, threshold=f"< {cfg.ASSET_PLAY_PB_MAX}")
    )

    ratio = metrics.get("net_cash_price_ratio")
    ratio_ok = ratio is not None and ratio >= cfg.ASSET_PLAY_NET_CASH_PRICE_MIN
    checks.append(
        _check(
            "net_cash_to_price",
            ratio_ok,
            value=ratio,
            threshold=f">= {cfg.ASSET_PLAY_NET_CASH_PRICE_MIN:.0%} of share price",
        )
    )

    return all(c["passed"] for c in checks), checks


QUALITATIVE_OVERLAY = [
    "Is the business easy to understand — or in a boring niche others overlook?",
    "Does the company have a durable local monopoly or recurring customer demand?",
    "Are acquisitions staying close to the core business (avoid diworseification)?",
    "Would you be comfortable holding this through a downturn if the story is intact?",
]


def assign_categories(metrics: dict) -> list[str]:
    categories = []
    if classify_fast_grower(metrics)[0]:
        categories.append("fast_grower")
    if classify_stalwart(metrics)[0]:
        categories.append("stalwart")
    if classify_asset_play(metrics)[0]:
        categories.append("asset_play")
    return categories
