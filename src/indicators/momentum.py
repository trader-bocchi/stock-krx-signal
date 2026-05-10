import pandas as pd
import numpy as np


def _linreg_value(series: pd.Series, period: int) -> pd.Series:
    """
    Linear regression value (end-point of linreg line) for a rolling window.
    Vectorized via numpy polyfit over rolling windows.
    """
    x = np.arange(period)
    result = np.full(len(series), np.nan)
    arr = series.to_numpy()
    for i in range(period - 1, len(arr)):
        y = arr[i - period + 1: i + 1]
        if np.any(np.isnan(y)):
            continue
        slope, intercept = np.polyfit(x, y, 1)
        result[i] = slope * (period - 1) + intercept
    return pd.Series(result, index=series.index)


class MomentumHistogram:
    """
    Squeeze Momentum indicator (LazyBear-style).

    momentum = LinearRegression(close - mean(SMA(close,period), mean(high,period), mean(low,period)), period)

    Positive and increasing → bullish momentum
    Negative and decreasing → bearish momentum
    """

    def __init__(self, period: int = 12):
        self.period = period

    def calculate(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
    ) -> pd.DataFrame:
        """
        Returns DataFrame with columns: momentum, momentum_prev, momentum_color
          momentum_color: 'green_up', 'green_down', 'red_down', 'red_up'
        """
        # LazyBear 원본 공식:
        # val = close - avg(avg(highest_high, lowest_low), SMA(close))
        # 즉 delta = close - ((midpoint + SMA) / 2)
        highest_high = high.rolling(self.period).max()
        lowest_low   = low.rolling(self.period).min()
        midpoint     = (highest_high + lowest_low) / 2
        reference    = (midpoint + close.rolling(self.period).mean()) / 2
        delta        = close - reference

        momentum = _linreg_value(delta, self.period)
        momentum_prev = momentum.shift(1)

        # Color coding (LazyBear convention)
        color = pd.Series("gray", index=close.index)
        pos_up = (momentum > 0) & (momentum > momentum_prev)
        pos_dn = (momentum > 0) & (momentum <= momentum_prev)
        neg_dn = (momentum <= 0) & (momentum < momentum_prev)
        neg_up = (momentum <= 0) & (momentum >= momentum_prev)
        color[pos_up] = "green_up"
        color[pos_dn] = "green_down"
        color[neg_dn] = "red_down"
        color[neg_up] = "red_up"

        return pd.DataFrame({
            "momentum": momentum,
            "momentum_prev": momentum_prev,
            "momentum_color": color,
        }, index=close.index)
