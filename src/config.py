from pathlib import Path
from typing import Any
import yaml


class Config:
    """Loads settings.yaml and provides typed accessors."""

    def __init__(self, path: str = "config/settings.yaml"):
        with open(path, encoding="utf-8") as f:
            self._data = yaml.safe_load(f)

    def get(self, *keys: str, default: Any = None) -> Any:
        node = self._data
        for k in keys:
            if not isinstance(node, dict):
                return default
            node = node.get(k, default)
        return node

    @property
    def strategy(self) -> dict:
        return self._data.get("strategy", {})

    @property
    def backtest(self) -> dict:
        return self._data.get("backtest", {})

    @property
    def data(self) -> dict:
        return self._data.get("data", {})

    @property
    def walk_forward(self) -> dict:
        return self._data.get("walk_forward", {})
