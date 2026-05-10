import logging
import time
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
import yfinance as yf
from tqdm import tqdm

from .base import DataProvider
from .cache_manager import CacheManager

logger = logging.getLogger(__name__)

_PERIOD_TIMEDELTA: dict[str, timedelta] = {
    "1mo":  timedelta(days=30),
    "3mo":  timedelta(days=91),
    "6mo":  timedelta(days=182),
    "1y":   timedelta(days=365),
    "2y":   timedelta(days=730),
    "5y":   timedelta(days=1825),
}


class USDataProvider(DataProvider):
    """
    yfinance-based provider for US equities and ETFs.
    Supports caching to avoid redundant API calls.
    """

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        self.cache = cache_manager or CacheManager()

    def fetch(
        self,
        ticker: str,
        period: str = "2y",
        interval: str = "1d",
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        cache_period = f"{period}_{end_date}" if end_date else period
        cached = self.cache.get(ticker, cache_period, interval)
        if cached is not None:
            logger.debug(f"[US] Cache hit: {ticker}")
            return cached

        logger.info(f"[US] Fetching {ticker} ({period}, {interval}{', as_of=' + end_date if end_date else ''})…")
        try:
            if end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                start_dt = end_dt - _PERIOD_TIMEDELTA.get(period, timedelta(days=730))
                raw = yf.download(
                    ticker,
                    start=start_dt.strftime("%Y-%m-%d"),
                    end=end_date,
                    interval=interval,
                    auto_adjust=True,
                    progress=False,
                )
            else:
                raw = yf.download(
                    ticker,
                    period=period,
                    interval=interval,
                    auto_adjust=True,
                    progress=False,
                )
            if raw.empty:
                raise ValueError(f"No data returned for {ticker}")
            # yfinance returns MultiIndex columns when downloading single tickers
            # with auto_adjust=True; flatten if needed
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            df = self.validate_ohlcv(raw)
            self.cache.set(ticker, cache_period, interval, df)
            return df
        except Exception as e:
            logger.error(f"[US] Failed to fetch {ticker}: {e}")
            raise

    def fetch_4h(
        self,
        ticker: str,
        lookback_days: int = 59,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        4시간 봉 데이터.
        yfinance는 4H를 직접 지원하지 않으므로 1H를 받아 4H로 리샘플링.
        yfinance 1H 최대 조회 기간: 730일 (실용적으로 60일 이하 권장)
        """
        cache_key = f"4h_{lookback_days}d" + (f"_{end_date}" if end_date else "")
        cached = self.cache.get(ticker, cache_key, "4h")
        if cached is not None:
            logger.debug(f"[US] Cache hit: {ticker} 4H")
            return cached

        logger.info(f"[US] Fetching {ticker} (4H, {lookback_days}d{', as_of=' + end_date if end_date else ''})…")
        try:
            if end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                start_dt = end_dt - timedelta(days=lookback_days)
                raw_1h = yf.download(
                    ticker,
                    start=start_dt.strftime("%Y-%m-%d"),
                    end=end_date,
                    interval="1h",
                    auto_adjust=True,
                    progress=False,
                )
            else:
                raw_1h = yf.download(
                    ticker,
                    period=f"{lookback_days}d",
                    interval="1h",
                    auto_adjust=True,
                    progress=False,
                )
            if raw_1h.empty:
                raise ValueError(f"No 1H data for {ticker}")
            if isinstance(raw_1h.columns, pd.MultiIndex):
                raw_1h.columns = raw_1h.columns.get_level_values(0)

            # 1H → 4H 리샘플링
            raw_4h = raw_1h.resample("4h").agg({
                "Open": "first",
                "High": "max",
                "Low": "min",
                "Close": "last",
                "Volume": "sum",
            }).dropna()

            df = self.validate_ohlcv(raw_4h)
            self.cache.set(ticker, cache_key, "4h", df)
            return df
        except Exception as e:
            logger.error(f"[US] Failed to fetch 4H {ticker}: {e}")
            raise

    def fetch_multiple_4h(
        self,
        tickers: list[str],
        lookback_days: int = 59,
        request_delay: float = 0.5,
        end_date: Optional[str] = None,
    ) -> dict[str, pd.DataFrame]:
        results: dict[str, pd.DataFrame] = {}
        for i, ticker in enumerate(tqdm(tickers, desc="US 4H fetch")):
            try:
                results[ticker] = self.fetch_4h(ticker, lookback_days, end_date=end_date)
            except Exception as e:
                logger.warning(f"[US] Skipping {ticker} 4H: {e}")
            if i < len(tickers) - 1:
                time.sleep(request_delay)
        return results

    def fetch_multiple(
        self,
        tickers: list[str],
        period: str = "2y",
        interval: str = "1d",
        request_delay: float = 0.5,
        end_date: Optional[str] = None,
    ) -> dict[str, pd.DataFrame]:
        """
        request_delay: 종목 간 딜레이(초). GitHub Actions 환경에서 rate-limit 방지.
        """
        results: dict[str, pd.DataFrame] = {}
        for i, ticker in enumerate(tqdm(tickers, desc="US fetch")):
            try:
                results[ticker] = self.fetch(ticker, period, interval, end_date=end_date)
            except Exception as e:
                logger.warning(f"[US] Skipping {ticker}: {e}")
            if i < len(tickers) - 1:
                time.sleep(request_delay)
        return results
