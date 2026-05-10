import pandas as pd
import numpy as np


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


class KeltnerChannel:
    """
    Keltner Channel using EMA(close) ± atr_mult × ATR.

    mid   = EMA(close, period)
    upper = mid + atr_mult * ATR(period)
    lower = mid - atr_mult * ATR(period)
    """

    def __init__(self, period: int = 20, atr_mult: float = 1.5, atr_period: int = 14):
        self.period = period
        self.atr_mult = atr_mult
        self.atr_period = atr_period

    def calculate(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
    ) -> pd.DataFrame:
        """
        Returns DataFrame with columns: kc_mid, kc_upper, kc_lower, atr
        """
        mid = close.ewm(span=self.period, adjust=False).mean()
        atr = _atr(high, low, close, self.atr_period)
        upper = mid + self.atr_mult * atr
        lower = mid - self.atr_mult * atr

        return pd.DataFrame({
            "kc_mid": mid,
            "kc_upper": upper,
            "kc_lower": lower,
            "atr": atr,
        }, index=close.index)
