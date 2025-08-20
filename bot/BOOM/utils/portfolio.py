import json
from pathlib import Path
from typing import List, Dict

TRADE_FILE = Path("trade_log.json")


class PortfolioStats:
    """Read trade_log.json and compute aggregate performance."""

    def __init__(self):
        self.trades: List[Dict] = self._load()

    # ------------- public interface ---------------------------------
    @property
    def closed(self):
        return [t for t in self.trades if t["status"] == "closed"]

    @property
    def open(self):
        return [t for t in self.trades if t["status"] == "open"]

    def total_realized_pl(self) -> float:
        return sum(t["profit_loss"] for t in self.closed)

    def win_rate(self) -> float:
        if not self.closed:
            return 0.0
        winners = [t for t in self.closed if t["profit_loss"] > 0]
        return len(winners) / len(self.closed)

    def summary(self) -> str:
        return (
            f"\n========== PORTFOLIO SUMMARY ==========\n"
            f"Closed trades  : {len(self.closed)}\n"
            f"Open trades    : {len(self.open)}\n"
            f"Win-rate       : {self.win_rate():.2%}\n"
            f"Total P&L (USDT): {self.total_realized_pl():.6f}\n"
            f"========================================"
        )

    # ------------- helpers ------------------------------------------
    def _load(self) -> List[Dict]:
        if TRADE_FILE.exists():
            with TRADE_FILE.open() as f:
                return json.load(f)
        return []
