import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False, min_periods=window).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window, min_periods=window).mean()


def resample_weekly(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Resample daily OHLCV to weekly (Friday close)."""
    df = daily_df.set_index("Date").sort_index()
    weekly = df.resample("W-FRI").agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
    )
    weekly = weekly.dropna(subset=["Close"]).reset_index()
    weekly.rename(columns={"Date": "Date"}, inplace=True)
    if "ticker" in daily_df.columns:
        weekly["ticker"] = daily_df["ticker"].iloc[0]
    return weekly


def return_over_days(series: pd.Series, days: int) -> float | None:
    if len(series) <= days:
        return None
    start = series.iloc[-days - 1]
    end = series.iloc[-1]
    if start == 0 or pd.isna(start) or pd.isna(end):
        return None
    return (end / start) - 1


def range_52w(df: pd.DataFrame, lookback: int = 252) -> tuple[float, float]:
    window = df.tail(lookback)
    return float(window["High"].max()), float(window["Low"].min())


def distance_from_high_pct(price: float, high: float) -> float | None:
    if high == 0:
        return None
    return (high - price) / high


def pct_above_low(price: float, low: float) -> float | None:
    if low == 0:
        return None
    return (price - low) / low


def bollinger_bands(
    close: pd.Series,
    window: int = 20,
    num_std: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (upper, mid, lower) Bollinger bands."""
    mid = sma(close, window)
    std = close.rolling(window, min_periods=window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def bollinger_width(close: pd.Series, window: int = 20) -> pd.Series:
    upper, mid, lower = bollinger_bands(close, window)
    return (upper - lower) / mid


def macd_histogram(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    """MACD histogram (MACD line minus signal line)."""
    fast_ema = ema(close, fast)
    slow_ema = ema(close, slow)
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return macd_line - signal_line


def find_swing_lows(lows: pd.Series, order: int = 2) -> list[tuple[int, float]]:
    """Local minima using a symmetric window of `order` bars on each side."""
    values = lows.to_numpy()
    swings: list[tuple[int, float]] = []
    for i in range(order, len(values) - order):
        window = values[i - order : i + order + 1]
        if values[i] == np.min(window):
            swings.append((i, float(values[i])))
    return swings


def find_swing_highs(highs: pd.Series, order: int = 2) -> list[tuple[int, float]]:
    """Local maxima using a symmetric window of `order` bars on each side."""
    values = highs.to_numpy()
    swings: list[tuple[int, float]] = []
    for i in range(order, len(values) - order):
        window = values[i - order : i + order + 1]
        if values[i] == np.max(window):
            swings.append((i, float(values[i])))
    return swings


def is_rising(series: pd.Series, lookback: int = 5) -> bool:
    if len(series) < lookback + 1:
        return False
    return float(series.iloc[-1]) > float(series.iloc[-lookback - 1])
