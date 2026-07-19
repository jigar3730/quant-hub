from __future__ import annotations

import pandas as pd

from quant_hub.engine.types import ScanResult, TickerResult


def scan_result_to_dataframe(result: ScanResult) -> pd.DataFrame:
    if not result.tickers:
        return pd.DataFrame()

    rows = [t.to_row_dict() for t in result.tickers]
    df = pd.DataFrame(rows)

    score_cols = _score_columns_for_strategy(result.strategy_id)
    for col in score_cols:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = df[col].fillna(0.0)

    eligible = df[df["eligible"]].copy()
    filtered = df[~df["eligible"]].copy()

    sort_cols = []
    ascending = []
    for key in _sort_keys_for_strategy(result.strategy_id):
        if key in df.columns:
            sort_cols.append(key)
            ascending.append(False)

    if sort_cols and not eligible.empty:
        eligible = eligible.sort_values(by=sort_cols, ascending=ascending)
    if not filtered.empty:
        filtered = filtered.sort_values(by="ticker")

    if eligible.empty and filtered.empty:
        return df
    if eligible.empty:
        return filtered.reset_index(drop=True)
    if filtered.empty:
        return eligible.reset_index(drop=True)
    return pd.concat([eligible, filtered], ignore_index=True)


def _sort_keys_for_strategy(strategy_id: str) -> list[str]:
    if strategy_id == "launchpad":
        return ["final_adjusted_score", "macd_zero_line_score", "squeeze_intensity_score"]
    return ["final_adjusted_score"]


def _score_columns_for_strategy(strategy_id: str) -> list[str]:
    if strategy_id == "launchpad":
        from quant_hub.strategies.launchpad.aggregate import LAUNCHPAD_SCORE_COLUMNS

        return LAUNCHPAD_SCORE_COLUMNS
    return []


def ticker_results_to_legacy_scores(tickers: list[TickerResult]) -> dict[str, dict[str, float]]:
    return {t.ticker: t.to_legacy_scores_dict() for t in tickers if t.eligible}
