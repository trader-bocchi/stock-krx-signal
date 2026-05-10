import logging
import pandas as pd
import numpy as np
from typing import Optional

from .metrics import PerformanceMetrics

logger = logging.getLogger(__name__)


class BacktestEngine:
    """
    Vectorized backtest engine.

    Design rules (no lookahead bias):
    - Signals are generated on bar N's close
    - Execution is on bar N+1's open
    - Cost model: commission + slippage on both entry and exit

    Supports:
    - Single-position model (one position at a time)
    - Stop-loss
    - Take-profit (optional)
    """

    def __init__(
        self,
        initial_capital: float = 100_000_000,
        commission: float = 0.0025,
        slippage: float = 0.001,
        position_size: float = 0.1,
        stop_loss: Optional[float] = 0.05,
        take_profit: Optional[float] = None,
    ):
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.position_size = position_size
        self.stop_loss = stop_loss
        self.take_profit = take_profit

    def run(self, data: pd.DataFrame, ticker: str = "UNKNOWN") -> PerformanceMetrics:
        """
        Args:
            data: output from SignalEngine.generate() — must contain
                  open, close, long_signal, exit_signal columns.
            ticker: for labeling in metrics

        Returns:
            PerformanceMetrics instance
        """
        trades = []
        equity = self.initial_capital

        in_position = False
        entry_price: float = 0.0
        entry_date = None

        equity_series = {}

        for date, row in data.iterrows():
            equity_series[date] = equity

            if not in_position:
                if row.get("long_signal", False):
                    # Enter on open of this bar (signal was set on previous close)
                    exec_price = row["open"] * (1 + self.slippage)
                    total_cost = exec_price * (1 + self.commission)
                    entry_price = total_cost
                    entry_date = date
                    in_position = True

            else:
                # Check stop loss intrabar
                if self.stop_loss and row["low"] <= entry_price * (1 - self.stop_loss):
                    exit_price = entry_price * (1 - self.stop_loss)
                    exit_price *= (1 - self.slippage) * (1 - self.commission)
                    ret = (exit_price / entry_price) - 1
                    trades.append({
                        "entry_date": entry_date,
                        "exit_date": date,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "return_pct": ret,
                        "exit_reason": "stop_loss",
                    })
                    equity *= (1 + ret * self.position_size)
                    in_position = False
                    continue

                # Check take profit
                if self.take_profit and row["high"] >= entry_price * (1 + self.take_profit):
                    exit_price = entry_price * (1 + self.take_profit)
                    exit_price *= (1 - self.slippage) * (1 - self.commission)
                    ret = (exit_price / entry_price) - 1
                    trades.append({
                        "entry_date": entry_date,
                        "exit_date": date,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "return_pct": ret,
                        "exit_reason": "take_profit",
                    })
                    equity *= (1 + ret * self.position_size)
                    in_position = False
                    continue

                # Normal exit signal
                if row.get("exit_signal", False):
                    exit_price = row["open"] * (1 - self.slippage) * (1 - self.commission)
                    ret = (exit_price / entry_price) - 1
                    trades.append({
                        "entry_date": entry_date,
                        "exit_date": date,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "return_pct": ret,
                        "exit_reason": "signal",
                    })
                    equity *= (1 + ret * self.position_size)
                    in_position = False

        # Force close any open position at end
        if in_position:
            last_row = data.iloc[-1]
            exit_price = last_row["close"] * (1 - self.slippage) * (1 - self.commission)
            ret = (exit_price / entry_price) - 1
            trades.append({
                "entry_date": entry_date,
                "exit_date": data.index[-1],
                "entry_price": entry_price,
                "exit_price": exit_price,
                "return_pct": ret,
                "exit_reason": "end_of_data",
            })
            equity *= (1 + ret * self.position_size)

        # Build results
        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame(
            columns=["entry_date", "exit_date", "entry_price", "exit_price", "return_pct", "exit_reason"]
        )
        equity_curve = pd.Series(equity_series)

        if trades_df.empty:
            logger.warning(f"[{ticker}] No trades executed.")

        return PerformanceMetrics.from_trades(
            ticker=ticker,
            trades=trades_df,
            equity_curve=equity_curve,
            initial_capital=self.initial_capital,
        )
