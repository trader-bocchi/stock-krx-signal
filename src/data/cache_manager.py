import os
import hashlib
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import pandas as pd


class CacheManager:
    """Pickle-based local cache for OHLCV DataFrames."""

    def __init__(self, cache_dir: str = "data/cache", expiry_hours: int = 12):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.expiry_hours = expiry_hours

    def _key(self, ticker: str, period: str, interval: str) -> str:
        raw = f"{ticker}_{period}_{interval}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.pkl"

    def get(self, ticker: str, period: str, interval: str) -> Optional[pd.DataFrame]:
        key = self._key(ticker, period, interval)
        path = self._path(key)
        if not path.exists():
            return None
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if datetime.now() - mtime > timedelta(hours=self.expiry_hours):
            path.unlink(missing_ok=True)
            return None
        with open(path, "rb") as f:
            return pickle.load(f)

    def set(self, ticker: str, period: str, interval: str, df: pd.DataFrame) -> None:
        key = self._key(ticker, period, interval)
        with open(self._path(key), "wb") as f:
            pickle.dump(df, f)

    def clear(self, ticker: Optional[str] = None) -> None:
        if ticker is None:
            for p in self.cache_dir.glob("*.pkl"):
                p.unlink()
        else:
            # clear all intervals for this ticker
            for interval in ["1d", "1wk", "60m"]:
                for period in ["1y", "2y", "3y", "5y"]:
                    key = self._key(ticker, period, interval)
                    self._path(key).unlink(missing_ok=True)
