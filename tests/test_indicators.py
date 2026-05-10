"""Unit tests for indicator correctness (no lookahead bias check)."""
import numpy as np
import pandas as pd
import pytest

from src.indicators.bollinger import BollingerBands
from src.indicators.keltner import KeltnerChannel
from src.indicators.momentum import MomentumHistogram
from src.indicators.squeeze import SqueezeDetector


def make_ohlcv(n: int = 300, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0, 2, n)
    low = close - rng.uniform(0, 2, n)
    open_ = close + rng.normal(0, 0.5, n)
    volume = rng.integers(1_000_000, 10_000_000, n).astype(float)
    idx = pd.date_range("2022-01-01", periods=n, freq="B")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx)


def test_bollinger_no_future_leak():
    df = make_ohlcv()
    bb = BollingerBands()
    result = bb.calculate(df["close"])
    # First 19 rows must be NaN (period=20)
    assert result["bb_mid"].iloc[:19].isna().all()
    assert result["bb_mid"].iloc[20:].notna().all()


def test_keltner_no_future_leak():
    df = make_ohlcv()
    kc = KeltnerChannel()
    result = kc.calculate(df["high"], df["low"], df["close"])
    assert result["kc_upper"].iloc[:13].isna().all()


def test_squeeze_columns_present():
    df = make_ohlcv()
    detector = SqueezeDetector()
    result = detector.calculate(df)
    for col in ["squeeze_on", "squeeze_release", "valid_release", "momentum"]:
        assert col in result.columns, f"Missing column: {col}"


def test_squeeze_no_lookahead():
    """Ensure that signal on bar N does not use bar N+1 data."""
    df = make_ohlcv(300)
    detector = SqueezeDetector()
    full = detector.calculate(df)
    partial = detector.calculate(df.iloc[:-1])

    # The last row of partial must match the second-to-last of full
    last_idx = partial.index[-1]
    assert full.loc[last_idx, "squeeze_on"] == partial.loc[last_idx, "squeeze_on"]
    assert abs(full.loc[last_idx, "momentum"] - partial.loc[last_idx, "momentum"]) < 1e-6
