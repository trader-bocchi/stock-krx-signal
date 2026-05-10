import pandas as pd
import numpy as np

from .bollinger import BollingerBands
from .keltner import KeltnerChannel
from .momentum import MomentumHistogram
from .volume import VolumeFilter


class SqueezeDetector:
    """
    Full Squeeze Momentum indicator calculator.

    Squeeze ON  : BB upper < KC upper AND BB lower > KC lower
    Squeeze OFF : squeeze just released (was ON, now OFF)
    """

    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        kc_period: int = 20,
        kc_atr_mult: float = 1.5,
        kc_atr_period: int = 14,
        momentum_period: int = 12,
        volume_ma_period: int = 20,
        volume_multiplier: float = 1.2,
        min_squeeze_bars: int = 3,
    ):
        self.bb = BollingerBands(bb_period, bb_std)
        self.kc = KeltnerChannel(kc_period, kc_atr_mult, kc_atr_period)
        self.mom = MomentumHistogram(momentum_period)
        self.vol = VolumeFilter(volume_ma_period, volume_multiplier)
        self.min_squeeze_bars = min_squeeze_bars

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Args:
            df: OHLCV DataFrame (columns: open, high, low, close, volume)

        Returns:
            Original df merged with all indicator columns + squeeze flags.
        """
        bb_df = self.bb.calculate(df["close"])
        kc_df = self.kc.calculate(df["high"], df["low"], df["close"])
        mom_df = self.mom.calculate(df["high"], df["low"], df["close"])
        vol_df = self.vol.calculate(df["volume"])

        result = pd.concat([df, bb_df, kc_df, mom_df, vol_df], axis=1)

        # Squeeze ON: BB inside KC
        result["squeeze_on"] = (
            (result["bb_upper"] < result["kc_upper"]) &
            (result["bb_lower"] > result["kc_lower"])
        )

        # Squeeze release: was ON previous bar, now OFF
        result["squeeze_release"] = (
            result["squeeze_on"].shift(1).fillna(False) &
            ~result["squeeze_on"]
        )

        # Count consecutive squeeze bars (for min_squeeze_bars filter)
        squeeze_count = result["squeeze_on"].astype(int)
        result["squeeze_bars"] = (
            squeeze_count
            .groupby((squeeze_count != squeeze_count.shift()).cumsum())
            .transform("cumsum")
        )

        # Valid release: squeeze lasted at least min_squeeze_bars
        result["valid_release"] = (
            result["squeeze_release"] &
            (result["squeeze_bars"].shift(1).fillna(0) >= self.min_squeeze_bars)
        )

        return result
