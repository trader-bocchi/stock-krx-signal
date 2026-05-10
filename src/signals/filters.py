import pandas as pd


class SignalFilters:
    """
    Additional filters applied on top of raw squeeze signals.
    Each method returns a boolean Series aligned to the input index.
    """

    @staticmethod
    def momentum_positive(df: pd.DataFrame) -> pd.Series:
        """Momentum histogram is positive (bullish zone)."""
        return df["momentum"] > 0

    @staticmethod
    def momentum_increasing(df: pd.DataFrame) -> pd.Series:
        """Momentum is increasing vs previous bar."""
        return df["momentum"] > df["momentum_prev"]

    @staticmethod
    def volume_surge(df: pd.DataFrame) -> pd.Series:
        """Volume is above its MA threshold."""
        return df["vol_surge"]

    @staticmethod
    def above_ema(df: pd.DataFrame, ema_period: int = 50) -> pd.Series:
        """Price is above EMA (trend filter)."""
        ema = df["close"].ewm(span=ema_period, adjust=False).mean()
        return df["close"] > ema

    @staticmethod
    def adr_filter(df: pd.DataFrame, min_adr_pct: float = 1.5) -> pd.Series:
        """
        Average Daily Range filter: ensures enough intraday volatility.
        ADR = mean((high - low) / close * 100, 10)
        """
        adr = ((df["high"] - df["low"]) / df["close"] * 100).rolling(10).mean()
        return adr >= min_adr_pct
