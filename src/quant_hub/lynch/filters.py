"""Peter Lynch quantitative filters and anti-filters."""

from __future__ import annotations

from quant_hub.lynch import config as cfg


def _check(
    rule: str,
    passed: bool,
    *,
    value,
    threshold: str,
    detail: str = "",
) -> dict:
    return {
        "rule": rule,
        "passed": passed,
        "value": value,
        "threshold": threshold,
        "detail": detail,
    }


def _growth_rate(metrics: dict) -> float | None:
    g = metrics.get("eps_growth_for_peg")
    if g is not None:
        return float(g)
    g = metrics.get("eps_growth_5y")
    return float(g) if g is not None else None


def apply_anti_filters(metrics: dict) -> tuple[bool, list[dict], str | None]:
    if metrics.get("error"):
        return False, [], metrics["error"]

    checks: list[dict] = []
    eps = metrics.get("trailing_eps")
    pe = metrics.get("pe_ratio")

    profitable = eps is not None and float(eps) > 0
    checks.append(
        _check(
            "positive_earnings",
            profitable,
            value=eps,
            threshold="trailing EPS > 0",
            detail="Lynch skipped money-losing story stocks unless turnaround was obvious.",
        )
    )

    roe = metrics.get("return_on_equity")
    roe_ok = roe is None or float(roe) >= cfg.ROE_MIN_ANTI
    checks.append(
        _check(
            "return_on_equity",
            roe_ok,
            value=roe,
            threshold=f">= {cfg.ROE_MIN_ANTI:.0%} when reported",
            detail="Weak returns on equity often mean a mediocre business model.",
        )
    )

    rev_cv = metrics.get("revenue_cv")
    rev_stable = rev_cv is None or float(rev_cv) <= cfg.REVENUE_CV_MAX
    checks.append(
        _check(
            "revenue_stability",
            rev_stable,
            value=rev_cv,
            threshold=f"revenue CV <= {cfg.REVENUE_CV_MAX}",
            detail="Highly lumpy revenue can mean fad demand or customer concentration.",
        )
    )

    if not profitable and (pe is None or float(pe) <= 0):
        return False, checks, "no_earnings"

    if not all(c["passed"] for c in checks):
        failed = next(c["rule"] for c in checks if not c["passed"])
        return False, checks, failed

    return True, checks, None


def apply_base_screen(metrics: dict) -> tuple[bool, list[dict], str | None]:
    if metrics.get("error"):
        return False, [], metrics["error"]

    checks: list[dict] = []
    peg = metrics.get("peg_ratio")
    peg_ok = peg is not None and float(peg) <= cfg.PEG_MAX
    checks.append(
        _check(
            "peg_ratio",
            peg_ok,
            value=peg,
            threshold=f"<= {cfg.PEG_MAX}",
            detail="Core Lynch rule: don't overpay for growth.",
        )
    )

    growth = _growth_rate(metrics)
    growth_ok = (
        growth is not None and cfg.EPS_GROWTH_MIN <= float(growth) <= cfg.EPS_GROWTH_MAX
    )
    checks.append(
        _check(
            "eps_growth_5y",
            growth_ok,
            value=_pct(growth),
            threshold=f"{cfg.EPS_GROWTH_MIN:.0%} – {cfg.EPS_GROWTH_MAX:.0%}",
            detail=metrics.get("eps_growth_source", "earnings growth"),
        )
    )

    pe = metrics.get("pe_ratio")
    pe_ok = pe is not None and 0 < float(pe) < cfg.PE_MAX
    checks.append(
        _check(
            "pe_ratio",
            pe_ok,
            value=pe,
            threshold=f"0 < P/E < {cfg.PE_MAX}",
            detail="Trailing P/E preferred; avoids negative or extreme multiples.",
        )
    )

    de = metrics.get("debt_to_equity")
    net_cash = metrics.get("net_cash")
    de_ok = de is not None and float(de) < cfg.DEBT_TO_EQUITY_MAX
    cash_ok = net_cash is not None and float(net_cash) > 0
    fin_ok = de_ok or cash_ok
    checks.append(
        _check(
            "financial_strength",
            fin_ok,
            value={"debt_to_equity": de, "net_cash": net_cash},
            threshold=f"D/E < {cfg.DEBT_TO_EQUITY_MAX:.0%} OR net cash > 0",
            detail="Replaces a strict 'net cash only' rule — most good companies carry some debt.",
        )
    )

    inst = metrics.get("institutional_ownership")
    analysts = metrics.get("analyst_count")
    if inst is None and analysts is None:
        neglected = True
        neglect_detail = "Coverage data missing — not penalized."
    else:
        neglected = False
        if inst is not None and float(inst) < cfg.INSTITUTIONAL_OWNERSHIP_MAX:
            neglected = True
        if analysts is not None and int(analysts) <= cfg.ANALYST_COVERAGE_MAX:
            neglected = True
        neglect_detail = "Lynch liked names not everyone was talking about."
    checks.append(
        _check(
            "wall_street_neglect",
            neglected,
            value={"institutional_pct": _pct(inst), "analysts": analysts},
            threshold=(
                f"inst < {cfg.INSTITUTIONAL_OWNERSHIP_MAX:.0%} "
                f"OR analysts <= {cfg.ANALYST_COVERAGE_MAX} (or data missing)"
            ),
            detail=neglect_detail,
        )
    )

    insider_buy = metrics.get("insider_purchases_6m")
    shares_chg = metrics.get("shares_outstanding_change_yoy")
    if insider_buy is None and shares_chg is None:
        alignment = True
        align_detail = "Insider/share data missing — not penalized."
    else:
        alignment = False
        if insider_buy is not None and float(insider_buy) > 0:
            alignment = True
        if shares_chg is not None and float(shares_chg) < 0:
            alignment = True
        align_detail = "Skin in the game or shrinking share count."
    checks.append(
        _check(
            "insider_or_buyback",
            alignment,
            value={"insider_purchases_6m": insider_buy, "shares_change_yoy": _pct(shares_chg)},
            threshold="insider buying > 0 OR shares outstanding declining (or data missing)",
            detail=align_detail,
        )
    )

    if not all(c["passed"] for c in checks):
        failed = next(c["rule"] for c in checks if not c["passed"])
        return False, checks, failed
    return True, checks, None


def _pct(value) -> str | float | None:
    if value is None:
        return None
    try:
        v = float(value)
        if abs(v) <= 1.5:
            return round(v * 100, 2)
        return round(v, 2)
    except (TypeError, ValueError):
        return value


def lynch_score(checks: list[dict]) -> float:
    if not checks:
        return 0.0
    passed = sum(1 for c in checks if c["passed"])
    return round(passed / len(checks) * 100, 1)
