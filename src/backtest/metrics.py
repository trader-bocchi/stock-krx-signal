import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PerformanceMetrics:
    """Aggregated performance statistics for a backtest run."""

    ticker: str
    total_return: float        # e.g. 0.35 = 35%
    cagr: float
    sharpe: float
    sortino: float
    max_drawdown: float        # negative value, e.g. -0.20
    win_rate: float
    profit_factor: float
    total_trades: int
    avg_trade_return: float
    avg_win: float
    avg_loss: float
    best_trade: float
    worst_trade: float
    equity_curve: pd.Series = field(repr=False, default=None)

    @classmethod
    def from_trades(
        cls,
        ticker: str,
        trades: pd.DataFrame,
        equity_curve: pd.Series,
        initial_capital: float = 100_000_000,
    ) -> "PerformanceMetrics":
        """
        Args:
            trades: DataFrame with columns [entry_date, exit_date, return_pct]
            equity_curve: Series of portfolio value over time
            initial_capital: starting capital
        """
        returns = trades["return_pct"]

        total_return = (equity_curve.iloc[-1] / initial_capital) - 1
        n_years = (equity_curve.index[-1] - equity_curve.index[0]).days / 365.25
        cagr = (1 + total_return) ** (1 / n_years) - 1 if n_years > 0 else 0.0

        daily_rets = equity_curve.pct_change().dropna()
        sharpe = _sharpe(daily_rets)
        sortino = _sortino(daily_rets)
        mdd = _max_drawdown(equity_curve)

        wins = returns[returns > 0]
        losses = returns[returns <= 0]
        win_rate = len(wins) / len(returns) if len(returns) else 0.0
        gross_profit = wins.sum() if len(wins) else 0.0
        gross_loss = abs(losses.sum()) if len(losses) else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf

        return cls(
            ticker=ticker,
            total_return=total_return,
            cagr=cagr,
            sharpe=sharpe,
            sortino=sortino,
            max_drawdown=mdd,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=len(returns),
            avg_trade_return=returns.mean() if len(returns) else 0.0,
            avg_win=wins.mean() if len(wins) else 0.0,
            avg_loss=losses.mean() if len(losses) else 0.0,
            best_trade=returns.max() if len(returns) else 0.0,
            worst_trade=returns.min() if len(returns) else 0.0,
            equity_curve=equity_curve,
        )

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "total_return": round(self.total_return * 100, 2),
            "cagr": round(self.cagr * 100, 2),
            "sharpe": round(self.sharpe, 3),
            "sortino": round(self.sortino, 3),
            "max_drawdown": round(self.max_drawdown * 100, 2),
            "win_rate": round(self.win_rate * 100, 2),
            "profit_factor": round(self.profit_factor, 3),
            "total_trades": self.total_trades,
            "avg_trade_return": round(self.avg_trade_return * 100, 2),
            "avg_win": round(self.avg_win * 100, 2),
            "avg_loss": round(self.avg_loss * 100, 2),
            "best_trade": round(self.best_trade * 100, 2),
            "worst_trade": round(self.worst_trade * 100, 2),
        }


# --- Helper functions ---

def _sharpe(daily_rets: pd.Series, risk_free: float = 0.0) -> float:
    excess = daily_rets - risk_free / 252
    if excess.std() == 0:
        return 0.0
    return float(excess.mean() / excess.std() * np.sqrt(252))


def _sortino(daily_rets: pd.Series, risk_free: float = 0.0) -> float:
    excess = daily_rets - risk_free / 252
    downside = excess[excess < 0]
    if len(downside) == 0 or downside.std() == 0:
        return np.inf
    return float(excess.mean() / downside.std() * np.sqrt(252))


def _max_drawdown(equity: pd.Series) -> float:
    roll_max = equity.cummax()
    drawdown = (equity - roll_max) / roll_max
    return float(drawdown.min())
