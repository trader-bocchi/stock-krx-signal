from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd


class DataProvider(ABC):
    """Abstract base class for all data providers."""

    @abstractmethod
    def fetch(
        self,
        ticker: str,
        period: str = "2y",
        interval: str = "1d",
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data for a single ticker.

        Returns:
            DataFrame with columns: open, high, low, close, volume
            Index: DatetimeIndex (UTC or local exchange time)
        """
        ...

    @abstractmethod
    def fetch_multiple(
        self,
        tickers: list[str],
        period: str = "2y",
        interval: str = "1d",
    ) -> dict[str, pd.DataFrame]:
        """Fetch OHLCV data for multiple tickers."""
        ...

    @staticmethod
    def validate_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names and drop rows with any NaN in OHLCV."""
        df.columns = [c.lower() for c in df.columns]
        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Missing OHLCV columns: {missing}")
        df = df[list(required)].copy()
        df.dropna(inplace=True)
        df.sort_index(inplace=True)
        return df
