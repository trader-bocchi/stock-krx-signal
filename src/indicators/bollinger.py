import pandas as pd
import numpy as np


class BollingerBands:
    """
    Standard Bollinger Bands.

    upper = SMA(close, period) + std_dev * σ(close, period)
    lower = SMA(close, period) - std_dev * σ(close, period)
    """

    def __init__(self, period: int = 20, std_dev: float = 2.0):
        self.period = period
        self.std_dev = std_dev

    def calculate(self, close: pd.Series) -> pd.DataFrame:
        """
        Returns DataFrame with columns: bb_mid, bb_upper, bb_lower, bb_width, bb_pct
        """
        mid = close.rolling(self.period).mean()
        std = close.rolling(self.period).std(ddof=0)
        upper = mid + self.std_dev * std
        lower = mid - self.std_dev * std
        width = (upper - lower) / mid
        pct = (close - lower) / (upper - lower)

        return pd.DataFrame({
            "bb_mid": mid,
            "bb_upper": upper,
            "bb_lower": lower,
            "bb_width": width,
            "bb_pct": pct,
        }, index=close.index)
