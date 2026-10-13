"""Synthetic price builders shared by the sector-swing tests (no network)."""

from __future__ import annotations

import numpy as np
import pandas as pd

END = pd.Timestamp("2026-09-18")  # a Friday: last completed session for the "Monday premarket" now
N_BARS = 260


def make_frame(
    ticker: str,
    closes,
    *,
    end: pd.Timestamp = END,
    volume: float = 5_000_000,
    wick: float = 0.003,
) -> pd.DataFrame:
    """Long-format OHLCV frame; Open = prior Close, wicks are +/- ``wick`` around the body."""
    closes = np.asarray(closes, dtype=float)
    dates = pd.bdate_range(end=end, periods=len(closes))
    opens = np.concatenate([[closes[0]], closes[:-1]])
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": opens,
            "High": np.maximum(opens, closes) * (1 + wick),
            "Low": np.minimum(opens, closes) * (1 - wick),
            "Close": closes,
            "Volume": volume,
            "ticker": ticker,
        }
    )


def path(start: float, daily: float, n: int = N_BARS, tail=(), *, seed=None, sigma=0.0):
    """Geometric drift for ``n - len(tail)`` bars (optionally noisy), then explicit % steps."""
    body = n - len(tail)
    rets = np.full(body, daily)
    if seed is not None:
        rets = rets + np.random.default_rng(seed).normal(0, sigma, body)
    closes = list(start * np.cumprod(1 + rets))
    for step in tail:
        closes.append(closes[-1] * (1 + step))
    return closes


def spy_closes(n: int = N_BARS) -> list[float]:
    return path(100, 0.0005, n)  # gentle uptrend: above SMA50 and SMA200


def bear_spy_closes(n: int = N_BARS) -> list[float]:
    """Up for 200 bars, then a sharp fall: close below both SMAs."""
    return path(100, 0.001, n, tail=(-0.02,) * 15)


# Tails (percent steps after a +0.4%/day trend) that land in each tier vs the SPY path above.
TAIL_TRIGGER = (-0.01, -0.01, -0.01, 0.0, 0.025)  # pullback to EMA20, then a strong turn up
TAIL_WIDE_STOP = (-0.012, -0.012, -0.012, -0.005, 0.03)  # valid trigger, stop > 2.5 ATR
TAIL_WATCH = (-0.012, -0.012, -0.012, -0.012, -0.002)  # pullback in progress, no trigger
TAIL_EXTENDED = (0.004,) * 5  # still ripping, never touched EMA20


def etf(ticker: str, tail=(), *, daily: float = 0.004, n: int = N_BARS, **kwargs) -> pd.DataFrame:
    return make_frame(ticker, path(50, daily, n, tail), **kwargs)


def market(*frames: pd.DataFrame, spy=None) -> pd.DataFrame:
    spy = spy_closes() if spy is None else spy
    return pd.concat([make_frame("SPY", spy), *frames], ignore_index=True)


def scenario(end: pd.Timestamp = END, spy=None, **etfs) -> pd.DataFrame:
    """SPY plus named ETFs on the +0.4%/day trend; ``etfs`` maps ticker -> tail steps."""
    frames = [etf(name, tail, end=end) for name, tail in etfs.items()]
    return pd.concat(
        [make_frame("SPY", spy_closes() if spy is None else spy, end=end), *frames],
        ignore_index=True,
    )


class FakeLoader:
    """price_loader stand-in: returns queued frames per call and records ``use_cache``."""

    def __init__(self, *responses: pd.DataFrame) -> None:
        self.responses = list(responses)
        self.calls: list[bool] = []

    def __call__(self, tickers, *, use_cache: bool = False) -> pd.DataFrame:
        self.calls.append(use_cache)
        return self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]
