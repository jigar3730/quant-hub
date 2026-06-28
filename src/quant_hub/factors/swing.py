from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_hub.engine.context import ScanContext
from quant_hub.factors.base import make_factor_result
from quant_hub.indicators import atr, ema, resample_weekly, rsi, return_over_days


def _rs_bucket(score_pct: float) -> float:
    if score_pct >= 0.90:
        return 20.0
    if score_pct >= 0.80:
        return 15.0
    if score_pct >= 0.60:
        return 10.0
    if score_pct >= 0.40:
        return 5.0
    return 0.0


@dataclass
class WeeklyTrendFactor:
    name: str = "trend"
    pass_kind: str = "ticker"

    def compute(self, ctx: ScanContext, ticker: str):
        df = ctx.stock_df(ticker)
        weekly = resample_weekly(df)
        w_close = weekly["Close"]
        ema20 = ema(w_close, 20)
        ema50 = ema(w_close, 50)
        rsi14 = rsi(w_close, 14)
        score = 0.0
        if float(ema20.iloc[-1]) > float(ema50.iloc[-1]):
            score += 7.0
        if len(ema50) >= 6 and float(ema50.iloc[-1]) > float(ema50.iloc[-6]):
            score += 4.0
        if float(rsi14.iloc[-1]) > 50:
            score += 4.0
        return make_factor_result(
            self.name,
            min(score, 15.0),
            15.0,
            ema20=float(ema20.iloc[-1]),
            ema50=float(ema50.iloc[-1]),
            rsi=float(rsi14.iloc[-1]),
        )


@dataclass
class SwingRelativeStrengthFactor:
    name: str = "relative_strength"
    pass_kind: str = "universe"

    def compute_universe(self, ctx: ScanContext, tickers: list[str]) -> dict:
        spy_close = ctx.spy_df["Close"]
        composite: dict[str, float] = {}
        for t in tickers:
            stock_close = ctx.stock_dfs[t]["Close"]
            r63 = return_over_days(stock_close, 63)
            r126 = return_over_days(stock_close, 126)
            r252 = return_over_days(stock_close, 252)
            spy63 = return_over_days(spy_close, 63)
            spy126 = return_over_days(spy_close, 126)
            spy252 = return_over_days(spy_close, 252)
            ratios = []
            if r63 is not None and spy63:
                ratios.append(r63 / spy63)
            if r126 is not None and spy126:
                ratios.append(r126 / spy126)
            if r252 is not None and spy252:
                ratios.append(r252 / spy252)
            composite[t] = sum(ratios) / len(ratios) if ratios else 0.0

        series = pd.Series(composite, dtype=float)
        if series.empty:
            return {}
        ranked = series.rank(pct=True, na_option="keep")
        return {
            t: make_factor_result(self.name, _rs_bucket(ranked[t]), 20.0, composite=composite[t])
            for t in tickers
        }


@dataclass
class PullbackQualityFactor:
    name: str = "pullback"
    pass_kind: str = "ticker"

    def compute(self, ctx: ScanContext, ticker: str):
        df = ctx.stock_df(ticker)
        close = df["Close"]
        ema20 = ema(close, 20)
        atr14 = atr(df, 14)
        price = float(close.iloc[-1])
        e20 = float(ema20.iloc[-1])
        dist_pct = abs((price - e20) / e20) * 100 if e20 else 99.0

        dist_score = 0.0
        if dist_pct <= 1:
            dist_score = 5.0
        elif dist_pct <= 2:
            dist_score = 4.0
        elif dist_pct <= 3:
            dist_score = 3.0
        elif dist_pct <= 5:
            dist_score = 1.0

        integrity_score = 5.0
        recent = df.tail(20)
        if (recent["Close"] < ema20.reindex(recent.index, method="ffill")).any():
            integrity_score = 3.0
        if (recent["Close"] < ema(close, 50).reindex(recent.index, method="ffill")).any():
            integrity_score = 0.0

        atr_val = float(atr14.iloc[-1]) if not pd.isna(atr14.iloc[-1]) else 0.0
        pullback_depth = (e20 - price) / atr_val if atr_val > 0 else 0.0
        atr_score = 0.0
        if 0 <= pullback_depth < 1:
            atr_score = 5.0
        elif pullback_depth < 1.5:
            atr_score = 3.0
        elif pullback_depth < 2:
            atr_score = 1.0

        total = min(dist_score + integrity_score + atr_score, 15.0)
        return make_factor_result(
            self.name,
            total,
            15.0,
            dist_pct=dist_pct,
            integrity=integrity_score,
            atr_pullback=pullback_depth,
        )


@dataclass
class PullbackVolumeFactor:
    name: str = "volume"
    pass_kind: str = "ticker"

    def compute(self, ctx: ScanContext, ticker: str):
        df = ctx.stock_df(ticker)
        recent = df.tail(21)
        avg20 = float(recent["Volume"].iloc[:-1].mean())
        today_vol = float(recent["Volume"].iloc[-1])
        ratio = today_vol / avg20 if avg20 else 1.0
        if ratio < 0.70:
            score = 10.0
        elif ratio < 0.85:
            score = 6.0
        elif ratio <= 1.1:
            score = 2.0
        else:
            score = 0.0
        return make_factor_result(self.name, score, 10.0, vol_ratio=ratio)
