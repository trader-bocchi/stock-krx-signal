import logging
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from ..backtest.metrics import PerformanceMetrics

logger = logging.getLogger(__name__)


class EdgeAnalyzer:
    """
    Computes a composite edge score for each ticker and ranks them.

    Edge score combines:
    - Sharpe ratio (risk-adjusted return)
    - CAGR
    - Win rate
    - Profit factor
    - Max drawdown (penalizes)
    - Total trades (penalizes < 5 trades → low statistical significance)
    """

    MIN_TRADES = 5

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or {
            "sharpe": 0.30,
            "cagr": 0.25,
            "win_rate": 0.15,
            "profit_factor": 0.15,
            "mdd_penalty": 0.15,
        }

    def score(self, metrics: PerformanceMetrics) -> float:
        """Compute normalized edge score [0, 1] for a single ticker."""
        if metrics.total_trades < self.MIN_TRADES:
            return 0.0

        # Normalize each component to [0, 1] range (rough, relative)
        sharpe_norm = self._clip_norm(metrics.sharpe, -1, 4)
        cagr_norm = self._clip_norm(metrics.cagr, -0.5, 2.0)
        wr_norm = self._clip_norm(metrics.win_rate, 0, 1)
        pf = min(metrics.profit_factor, 5.0) / 5.0
        mdd_norm = 1 - self._clip_norm(abs(metrics.max_drawdown), 0, 0.8)

        score = (
            self.weights["sharpe"] * sharpe_norm +
            self.weights["cagr"] * cagr_norm +
            self.weights["win_rate"] * wr_norm +
            self.weights["profit_factor"] * pf +
            self.weights["mdd_penalty"] * mdd_norm
        )
        return float(score)

    def rank(
        self,
        metrics_map: Dict[str, PerformanceMetrics],
        top_n: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Rank all tickers by edge score.

        Returns:
            DataFrame sorted by edge_score descending, with all key metrics.
        """
        rows = []
        for ticker, m in metrics_map.items():
            row = m.to_dict()
            row["edge_score"] = round(self.score(m), 4)
            rows.append(row)

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows).sort_values("edge_score", ascending=False)
        df = df.reset_index(drop=True)
        df.index += 1  # rank starts at 1

        if top_n:
            df = df.head(top_n)

        return df

    def print_report(self, ranking_df: pd.DataFrame) -> None:
        if ranking_df.empty:
            print("No results to display.")
            return
        cols = ["ticker", "edge_score", "sharpe", "cagr", "win_rate",
                "max_drawdown", "profit_factor", "total_trades"]
        available = [c for c in cols if c in ranking_df.columns]
        print("\n" + "=" * 70)
        print("  SQUEEZE MOMENTUM STRATEGY — TICKER EDGE RANKING")
        print("=" * 70)
        print(ranking_df[available].to_string(index=True))
        print("=" * 70 + "\n")

    @staticmethod
    def _clip_norm(value: float, low: float, high: float) -> float:
        return float(np.clip((value - low) / (high - low), 0, 1))
