from pathlib import Path
from typing import Dict, Optional
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from ..backtest.metrics import PerformanceMetrics


class PerformanceReport:
    """
    Generates performance reports: equity curves, drawdown, ranking charts.
    """

    def __init__(self, output_dir: str = "data/results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def plot_equity_curve(
        self,
        metrics: PerformanceMetrics,
        save: bool = True,
        show: bool = False,
    ) -> Optional[str]:
        if metrics.equity_curve is None:
            return None

        equity = metrics.equity_curve
        drawdown = (equity - equity.cummax()) / equity.cummax() * 100

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 7),
                                        gridspec_kw={"height_ratios": [3, 1]},
                                        sharex=True)
        fig.suptitle(
            f"{metrics.ticker} — Equity Curve  "
            f"(CAGR={metrics.cagr*100:.1f}%  Sharpe={metrics.sharpe:.2f}  "
            f"MDD={metrics.max_drawdown*100:.1f}%)",
            fontsize=12
        )

        ax1.plot(equity.index, equity / equity.iloc[0], color="#1f77b4", linewidth=1.5)
        ax1.axhline(1.0, color="gray", linestyle="--", linewidth=0.7)
        ax1.set_ylabel("Normalized Equity")
        ax1.grid(True, alpha=0.3)

        ax2.fill_between(drawdown.index, drawdown, 0, color="red", alpha=0.4)
        ax2.set_ylabel("Drawdown (%)")
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()

        if save:
            path = self.output_dir / f"{metrics.ticker}_equity.png"
            plt.savefig(path, dpi=150, bbox_inches="tight")
            plt.close()
            return str(path)

        if show:
            plt.show()
        plt.close()
        return None

    def plot_ranking_bar(
        self,
        ranking_df: pd.DataFrame,
        metric: str = "sharpe",
        top_n: int = 15,
        save: bool = True,
        show: bool = False,
    ) -> Optional[str]:
        df = ranking_df.head(top_n)
        if df.empty or metric not in df.columns:
            return None

        fig, ax = plt.subplots(figsize=(12, 6))
        colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in df[metric]]
        ax.barh(df["ticker"], df[metric], color=colors)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_xlabel(metric.upper())
        ax.set_title(f"Top {top_n} Tickers by {metric.upper()}")
        ax.grid(True, axis="x", alpha=0.3)
        plt.tight_layout()

        if save:
            path = self.output_dir / f"ranking_{metric}.png"
            plt.savefig(path, dpi=150, bbox_inches="tight")
            plt.close()
            return str(path)

        if show:
            plt.show()
        plt.close()
        return None

    def save_ranking_csv(self, ranking_df: pd.DataFrame, filename: str = "ranking.csv") -> str:
        path = self.output_dir / filename
        ranking_df.to_csv(path)
        return str(path)
