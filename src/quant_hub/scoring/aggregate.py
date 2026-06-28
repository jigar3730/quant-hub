from pathlib import Path

import pandas as pd

from quant_hub.regime.market import MarketRegime
from quant_hub.strategies.breakout.aggregate import build_results_table
from quant_hub.strategies.breakout.tiers import assign_tier_from_row as assign_tier

__all__ = ["assign_tier", "build_results_table", "export_results"]


def export_results(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path
