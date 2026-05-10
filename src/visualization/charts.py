from pathlib import Path
from typing import Optional
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import numpy as np


class SignalChart:
    """
    Plots price chart with BB/KC bands, squeeze indicator, and momentum histogram.
    """

    def __init__(self, output_dir: str = "data/results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def plot(
        self,
        data: pd.DataFrame,
        ticker: str,
        last_n_bars: int = 120,
        save: bool = True,
        show: bool = False,
    ) -> Optional[str]:
        """
        3-panel chart:
          1. Price + BB + KC + entry/exit markers
          2. Squeeze indicator (dots: red=on, green=off)
          3. Momentum histogram
        """
        df = data.tail(last_n_bars).copy()

        fig = plt.figure(figsize=(16, 10))
        fig.suptitle(f"{ticker} — Squeeze Momentum", fontsize=14, fontweight="bold")
        gs = gridspec.GridSpec(3, 1, height_ratios=[5, 1, 2], hspace=0.05)

        ax1 = fig.add_subplot(gs[0])
        ax2 = fig.add_subplot(gs[1], sharex=ax1)
        ax3 = fig.add_subplot(gs[2], sharex=ax1)

        x = range(len(df))
        dates = df.index

        # --- Panel 1: Price + Bands ---
        ax1.plot(x, df["close"], color="#1f77b4", linewidth=1.5, label="Close")
        ax1.fill_between(x, df["bb_upper"], df["bb_lower"],
                         alpha=0.15, color="blue", label="BB")
        ax1.plot(x, df["kc_upper"], color="orange", linestyle="--", linewidth=0.8, alpha=0.7)
        ax1.plot(x, df["kc_lower"], color="orange", linestyle="--", linewidth=0.8, alpha=0.7,
                 label="KC")

        # Entry markers
        if "long_signal" in df.columns:
            entries = df[df["long_signal"]]
            ax1.scatter(
                [x[df.index.get_loc(i)] for i in entries.index],
                entries["close"],
                marker="^", color="lime", s=100, zorder=5, label="Entry"
            )
        if "exit_signal" in df.columns:
            exits = df[df["exit_signal"]]
            ax1.scatter(
                [x[df.index.get_loc(i)] for i in exits.index],
                exits["close"],
                marker="v", color="red", s=100, zorder=5, label="Exit"
            )

        ax1.set_ylabel("Price")
        ax1.legend(loc="upper left", fontsize=8)
        ax1.grid(True, alpha=0.3)

        # --- Panel 2: Squeeze dots ---
        for i, (_, row) in enumerate(df.iterrows()):
            color = "red" if row.get("squeeze_on", False) else "lime"
            ax2.plot(i, 0.5, "o", color=color, markersize=5)

        ax2.set_ylim(0, 1)
        ax2.set_yticks([])
        ax2.set_ylabel("SQZ", fontsize=8)
        red_patch = mpatches.Patch(color="red", label="Squeeze ON")
        green_patch = mpatches.Patch(color="lime", label="Squeeze OFF")
        ax2.legend(handles=[red_patch, green_patch], loc="upper left", fontsize=7)

        # --- Panel 3: Momentum histogram ---
        if "momentum" in df.columns:
            for i, (_, row) in enumerate(df.iterrows()):
                val = row["momentum"]
                if pd.isna(val):
                    continue
                color_map = {
                    "green_up": "#00c853",
                    "green_down": "#69f0ae",
                    "red_down": "#d50000",
                    "red_up": "#ff6d00",
                }
                color = color_map.get(row.get("momentum_color", ""), "gray")
                ax3.bar(i, val, color=color, width=0.8)

            ax3.axhline(0, color="white", linewidth=0.5)
            ax3.set_ylabel("Momentum")
            ax3.grid(True, alpha=0.2)

        # X-axis labels
        tick_step = max(1, len(df) // 10)
        ax3.set_xticks(range(0, len(df), tick_step))
        ax3.set_xticklabels(
            [str(dates[i])[:10] for i in range(0, len(df), tick_step)],
            rotation=30, fontsize=7
        )

        plt.tight_layout()

        if save:
            path = self.output_dir / f"{ticker}_squeeze.png"
            plt.savefig(path, dpi=150, bbox_inches="tight")
            plt.close()
            return str(path)

        if show:
            plt.show()

        plt.close()
        return None
