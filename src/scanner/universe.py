import logging
from pathlib import Path
from typing import Dict, List, Optional
import yaml
import pandas as pd

logger = logging.getLogger(__name__)


class UniverseManager:
    """
    Loads and filters the stock universe from config yaml files.
    Supports both US and KR markets.
    """

    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self._us_config: Optional[dict] = None
        self._kr_config: Optional[dict] = None

    def _load(self, market: str) -> dict:
        path = self.config_dir / f"universe_{market}.yaml"
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    @property
    def us_config(self) -> dict:
        if self._us_config is None:
            self._us_config = self._load("us")
        return self._us_config

    @property
    def kr_config(self) -> dict:
        if self._kr_config is None:
            self._kr_config = self._load("kr")
        return self._kr_config

    def get_us_tickers(self, sectors: Optional[List[str]] = None) -> List[str]:
        tickers_by_sector = self.us_config.get("tickers", {})
        if sectors:
            return [t for s in sectors for t in tickers_by_sector.get(s, [])]
        return [t for ts in tickers_by_sector.values() for t in ts]

    def get_kr_tickers(self, sectors: Optional[List[str]] = None) -> List[str]:
        tickers_by_sector = self.kr_config.get("tickers", {})
        if sectors:
            return [t for s in sectors for t in tickers_by_sector.get(s, [])]
        return [t for ts in tickers_by_sector.values() for t in ts]

    def filter_by_liquidity(
        self,
        data_map: Dict[str, pd.DataFrame],
        market: str = "us",
    ) -> Dict[str, pd.DataFrame]:
        """
        Apply liquidity filters from the universe config.
        Removes tickers that don't meet minimum data/volume requirements.
        """
        config = self.us_config if market == "us" else self.kr_config
        filters = config.get("filters", {})
        min_data_days = filters.get("min_data_days", 252)
        min_price = filters.get("min_price", 1)

        filtered = {}
        for ticker, df in data_map.items():
            if len(df) < min_data_days:
                logger.debug(f"[{market}] {ticker}: insufficient data ({len(df)} bars)")
                continue
            if df["close"].iloc[-1] < min_price:
                logger.debug(f"[{market}] {ticker}: price below minimum")
                continue
            if market == "us":
                min_vol = filters.get("min_avg_volume", 5_000_000)
                avg_vol = df["volume"].tail(60).mean()
                if avg_vol < min_vol:
                    logger.debug(f"[US] {ticker}: avg volume {avg_vol:.0f} < {min_vol}")
                    continue
            filtered[ticker] = df

        logger.info(
            f"[{market}] Universe after filter: {len(filtered)}/{len(data_map)} tickers"
        )
        return filtered

    def scan_active_squeezes(
        self,
        signal_data_map: Dict[str, pd.DataFrame],
        lookback_bars: int = 3,
    ) -> List[Dict]:
        """
        Return list of tickers currently in squeeze (squeeze_on for last N bars).
        Used for real-time monitoring.
        """
        active = []
        for ticker, data in signal_data_map.items():
            if len(data) < lookback_bars:
                continue
            recent = data.tail(lookback_bars)
            if recent["squeeze_on"].all():
                last = data.iloc[-1]
                active.append({
                    "ticker": ticker,
                    "close": last["close"],
                    "momentum": last.get("momentum", None),
                    "squeeze_bars": last.get("squeeze_bars", None),
                })
        return active
