import logging
import time
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
from tqdm import tqdm

from .base import DataProvider
from .cache_manager import CacheManager

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BASE_SEC = 2.0


class KRDataProvider(DataProvider):
    """
    pykrx-based provider for KOSPI/KOSDAQ equities and ETFs.
    Ticker는 6자리 종목코드 사용 (e.g. '005930' for 삼성전자).
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
            logger.debug(f"[KR] Cache hit: {ticker}")
            return cached

        logger.info(f"[KR] Fetching {ticker} ({period}{', as_of=' + end_date if end_date else ''})…")
        try:
            from pykrx import stock as pykrx_stock
        except ImportError:
            raise ImportError("pykrx is not installed. Run: pip install pykrx")

        end_dt = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.today()
        start_dt = self._period_to_start(period, end_dt)
        start_str = start_dt.strftime("%Y%m%d")
        end_str = end_dt.strftime("%Y%m%d")

        last_exc: Exception = RuntimeError("Unknown error")
        for attempt in range(_MAX_RETRIES):
            try:
                raw = pykrx_stock.get_market_ohlcv_by_date(start_str, end_str, ticker)
                if raw.empty:
                    raise ValueError(f"No data returned for {ticker}")
                raw = raw.rename(columns={
                    "시가": "open",
                    "고가": "high",
                    "저가": "low",
                    "종가": "close",
                    "거래량": "volume",
                })
                df = self.validate_ohlcv(raw)
                self.cache.set(ticker, cache_period, interval, df)
                return df
            except ValueError:
                raise  # 데이터 없음은 재시도 불필요
            except Exception as e:
                last_exc = e
                wait = _RETRY_BASE_SEC ** attempt
                logger.warning(f"[KR] {ticker} 시도 {attempt + 1}/{_MAX_RETRIES} 실패 ({e}). {wait:.0f}초 후 재시도…")
                time.sleep(wait)

        logger.error(f"[KR] {ticker} 최종 실패: {last_exc}")
        raise last_exc

    def fetch_multiple(
        self,
        tickers: list[str],
        period: str = "2y",
        interval: str = "1d",
        end_date: Optional[str] = None,
    ) -> dict[str, pd.DataFrame]:
        results: dict[str, pd.DataFrame] = {}
        for ticker in tqdm(tickers, desc="KR fetch"):
            try:
                results[ticker] = self.fetch(ticker, period, interval, end_date=end_date)
            except Exception as e:
                logger.warning(f"[KR] Skipping {ticker}: {e}")
        return results

    @staticmethod
    def _period_to_start(period: str, end: datetime) -> datetime:
        mapping = {
            "1y": timedelta(days=365),
            "2y": timedelta(days=730),
            "3y": timedelta(days=1095),
            "5y": timedelta(days=1825),
        }
        delta = mapping.get(period, timedelta(days=730))
        return end - delta
