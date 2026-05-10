import logging
import pandas as pd

from ..indicators.squeeze import SqueezeDetector
from .filters import SignalFilters

logger = logging.getLogger(__name__)


class SignalEngine:
    """
    Generates long entry / exit signals using Squeeze Momentum strategy.

    Entry logic (all must be True, evaluated on bar close — no lookahead):
      1. valid_release (squeeze had >= min_squeeze_bars, just released)
      2. momentum > 0  (momentum in bullish zone)
      3. momentum increasing
      4. volume surge (optional, configurable)
      5. close > EMA(trend_ema_period) (optional trend filter)

    Exit logic (first of):
      - Momentum turns negative (primary)
      - Stop loss hit (based on entry price)
    """

    def __init__(
        self,
        squeeze_detector: SqueezeDetector,
        use_volume_filter: bool = True,
        use_trend_filter: bool = True,
        trend_ema_period: int = 50,
    ):
        self.detector = squeeze_detector
        self.use_volume_filter = use_volume_filter
        self.use_trend_filter = use_trend_filter
        self.trend_ema_period = trend_ema_period

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Args:
            df: OHLCV DataFrame

        Returns:
            DataFrame with all indicator columns + signal columns:
              long_signal  (bool) - entry signal
              exit_signal  (bool) - exit signal
        """
        data = self.detector.calculate(df)

        # --- Entry conditions ---
        entry = data["valid_release"].copy()
        entry &= SignalFilters.momentum_positive(data)
        entry &= SignalFilters.momentum_increasing(data)

        if self.use_volume_filter:
            entry &= SignalFilters.volume_surge(data)

        if self.use_trend_filter:
            entry &= SignalFilters.above_ema(data, self.trend_ema_period)

        # Shift by 1: signal fires on close of bar N → execute on open of bar N+1
        # This prevents lookahead bias in backtesting.
        data["long_signal"] = entry.shift(1).fillna(False)

        # --- Exit conditions ---
        # 모멘텀이 양수 → 음수로 전환되는 시점만 EXIT (단순 음수 지속 제외)
        mom_cross_down = (data["momentum"] < 0) & (data["momentum_prev"] >= 0)
        data["exit_signal"] = mom_cross_down.shift(1).fillna(False)

        # --- Live scanning columns (unshifted) ---
        # 라이브 스캔용: 현재 봉(N)의 조건 충족 여부 → 다음 봉(N+1) 시가에 진입/청산
        # long_signal[N] = entry[N-1] (백테스트 실행 타이밍)
        # scan_entry[N] = entry[N]   (라이브 스캔: 현재 봉 기준 → 다음 봉 진입)
        data["scan_entry"] = entry.fillna(False)
        data["scan_exit"] = mom_cross_down.fillna(False)

        logger.info(
            f"Signals generated: {data['long_signal'].sum()} entries, "
            f"{data['exit_signal'].sum()} exits "
            f"(scan_entry={data['scan_entry'].sum()}, scan_exit={data['scan_exit'].sum()})"
        )
        return data
