import pandas as pd


class VolumeFilter:
    """
    Volume analysis: relative volume and increasing volume conditions.
    """

    def __init__(self, ma_period: int = 20, multiplier: float = 1.2):
        self.ma_period = ma_period
        self.multiplier = multiplier

    def calculate(self, volume: pd.Series) -> pd.DataFrame:
        """
        Returns DataFrame with columns:
          vol_ma        - rolling mean volume
          vol_ratio     - current volume / vol_ma
          vol_surge     - bool: volume > multiplier * vol_ma
          vol_increasing- bool: volume > volume.shift(1)
        """
        vol_ma = volume.rolling(self.ma_period).mean()
        vol_ratio = volume / vol_ma
        vol_surge = vol_ratio >= self.multiplier
        vol_increasing = volume > volume.shift(1)

        return pd.DataFrame({
            "vol_ma": vol_ma,
            "vol_ratio": vol_ratio,
            "vol_surge": vol_surge,
            "vol_increasing": vol_increasing,
        }, index=volume.index)
