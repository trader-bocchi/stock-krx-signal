import logging
from dataclasses import dataclass
from typing import List
import pandas as pd

from .engine import BacktestEngine
from .metrics import PerformanceMetrics

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardResult:
    ticker: str
    folds: List[PerformanceMetrics]
    oos_sharpes: List[float]
    oos_cagrs: List[float]
    avg_oos_sharpe: float
    avg_oos_cagr: float


class WalkForwardValidator:
    """
    Walk-forward validation to prevent overfitting.

    Splits the dataset into n_splits sequential windows.
    Each window has an in-sample (IS) period for parameter selection
    and an out-of-sample (OOS) period for evaluation.

    IS ──────────────┐
                     │ OOS
                     └────────┐
                               │ OOS (next fold)
    """

    def __init__(
        self,
        backtest_engine: BacktestEngine,
        n_splits: int = 5,
        in_sample_ratio: float = 0.7,
    ):
        self.engine = backtest_engine
        self.n_splits = n_splits
        self.in_sample_ratio = in_sample_ratio

    def validate(
        self,
        data: pd.DataFrame,
        ticker: str = "UNKNOWN",
    ) -> WalkForwardResult:
        """
        Run walk-forward validation on pre-computed signal data.
        The same signal logic is used in all windows (no param optimization here),
        so this primarily checks stability of returns across time.
        """
        n = len(data)
        fold_size = n // self.n_splits
        folds = []

        for i in range(self.n_splits):
            start = i * fold_size
            end = start + fold_size if i < self.n_splits - 1 else n
            fold_data = data.iloc[start:end]

            split_idx = int(len(fold_data) * self.in_sample_ratio)
            oos_data = fold_data.iloc[split_idx:]

            if len(oos_data) < 30:
                logger.warning(f"[{ticker}] Fold {i}: OOS too small ({len(oos_data)} bars), skipping")
                continue

            metrics = self.engine.run(oos_data, ticker=f"{ticker}_fold{i}")
            folds.append(metrics)
            logger.info(
                f"[{ticker}] Fold {i} OOS → CAGR={metrics.cagr*100:.1f}%, "
                f"Sharpe={metrics.sharpe:.2f}, Trades={metrics.total_trades}"
            )

        oos_sharpes = [f.sharpe for f in folds]
        oos_cagrs = [f.cagr for f in folds]

        return WalkForwardResult(
            ticker=ticker,
            folds=folds,
            oos_sharpes=oos_sharpes,
            oos_cagrs=oos_cagrs,
            avg_oos_sharpe=sum(oos_sharpes) / len(oos_sharpes) if oos_sharpes else 0.0,
            avg_oos_cagr=sum(oos_cagrs) / len(oos_cagrs) if oos_cagrs else 0.0,
        )
