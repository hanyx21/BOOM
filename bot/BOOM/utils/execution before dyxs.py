"""
FakeExecution – a lightweight trade executor + portfolio tracker
================================================================
• coloured console output (green winners, red losers, yellow scratch)
• one-line live dashboard that refreshes every 0.5 s while positions are open
• accurate P/L to 8 dp stored in trade_log.json
• trail-stop & time-stop friendly (uses .get("trail_stop", …) safeguards)
"""

import json, time, winsound
from pathlib import Path
from typing  import List, Dict
from datetime import datetime

# ------------------------------------------------------------------ colours
try:                                 # works on Win & *nix if colourama installed
    from colorama import Fore, Style, init as _c_init
    _c_init(autoreset=True)
    GREEN = Fore.GREEN; RED = Fore.RED; YELLOW = Fore.YELLOW; CYAN = Fore.CYAN
except ImportError:                  # fallback – plain text
    GREEN = RED = YELLOW = CYAN = ''
    class Style: RESET_ALL = ''

# ------------------------------------------------------------------ constants
TRADE_FILE   = Path("trade_log.json")
MAX_HOLD_SEC = 900          # 15 min “breakeven or out” time-stop


class FakeExecution:
    """Simulate order execution and keep persistent trade / portfolio stats."""

    # -------------------------- lifecycle --------------------------
    def __init__(self, initial_balance: float):
        self.balance = initial_balance
        if TRADE_FILE.exists():
            with TRADE_FILE.open() as f:
                saved = json.load(f)
            self.trades    : List[Dict] = saved.get("trades", [])
            self.portfolio : Dict       = saved.get("portfolio", self._new_portfolio())
        else:
            self.trades    = []
            self.portfolio = self._new_portfolio()
            self._flush()

    # -------------------------- orders -----------------------------
    def execute_trade(self, action: str, symbol: str,
                      amount_usdt: float, price: float) -> None:
        """Create a new trade entry and print confirmation."""
        units = amount_usdt / price
        trade = {
            "symbol":   symbol,
            "action":   action,
            "amount_usdt": amount_usdt,
            "units":    units,
            "entry_price": price,
            "target_price": self.calculate_target_price(price),
            "status":   "open",
            "target_reached": False,
            "target_reached_price": None,
            "profit_loss": 0.0,
            "open_time": time.time()
        }
        self.trades.append(trade)

        print(f"{CYAN}[{datetime.now().strftime('%H:%M:%S')}]  "
              f"OPEN  {symbol:<12} @ {price:.6f}  size={amount_usdt:.2f} USDT{Style.RESET_ALL}")

        self._update_portfolio()
        self._flush()

    # -------------------------- tracking ---------------------------
    def track_positions(self, current_prices: Dict[str, float]) -> bool:
        """
        Update every open trade, close if target or time-stop hit,
        print a one-line dashboard.  Returns True when *all* positions flat.
        """
        all_closed = True
        now = time.time()
        dashboard: List[str] = []

        for t in self.trades:
            if t["status"] != "open":
                continue

            sym   = t["symbol"]
            price = current_prices.get(sym)            # latest mkt price
            if price is None:
                continue                               # skip if not in feed

            target = t["target_price"]

            # build dashboard entry BEFORE status may change
            pct = (price - t["entry_price"]) / t["entry_price"] * 100
            dashboard.append(f"{sym:<10}{price:>11.6f}{pct:+6.2f}% tgt {target:.6f}")

            # ---- target hit ------------------------------------------------
            if price >= target:
                self._close_trade(t, price, "target hit")
                continue

            # ---- 5-minute breakeven exit -----------------------------------
            held = now - t["open_time"]
            if held >= MAX_HOLD_SEC and price >= t["entry_price"]:
                self._close_trade(t, price, "time stop")
                continue

            all_closed = False

        # refresh portfolio + write file
        self._update_portfolio()
        self._flush()

        # ------ live dashboard – overwrite previous line --------------------
        if dashboard:
            print("\r" + " | ".join(dashboard), end="", flush=True)

        return all_closed

    # -------------------------- helpers ----------------------------
    @staticmethod
    def calculate_target_price(entry_price: float) -> float:
        """Fixed +0.2 % profit-target."""
        return entry_price * 1.002

    def has_open_positions(self) -> bool:
        return any(t["status"] == "open" for t in self.trades)

    def get_open_positions(self):
        return [t for t in self.trades if t["status"] == "open"]

    def recently_traded(self, symbol: str, cooldown_sec: int = 3600) -> bool:
        """True if <symbol> was opened within the last *cooldown_sec*."""
        now = time.time()
        for t in reversed(self.trades):          # newest first
            if t["symbol"] == symbol:
                return now - t["open_time"] < cooldown_sec
        return False

    # ---------------------- portfolio / P&L ------------------------
    def _close_trade(self, trade: Dict, exit_price: float, reason: str) -> None:
        trade["status"]               = "closed"
        trade["target_reached"]       = (reason == "target hit")
        trade["target_reached_price"] = exit_price

        spread = exit_price - trade["entry_price"]
        profit = round(spread * trade["units"], 8)
        trade["profit_loss"]          = profit
        trade["pct_move"]             = round(spread / trade["entry_price"] * 100, 3)
        trade["pct_gain"]             = round(profit / trade["amount_usdt"] * 100, 3)

        colour = GREEN if profit > 0 else (RED if profit < 0 else YELLOW)
        print(f"\n{colour}[{datetime.now().strftime('%H:%M:%S')}]  "
              f"CLOSE {trade['symbol']:<12} @ {exit_price:.6f}  "
              f"{reason:>12}  Δ={trade['pct_move']:+5.2f}%  "
              f"P/L={profit:.6f} USDT{Style.RESET_ALL}")

        winsound.Beep(1000, 300)

    def _update_portfolio(self) -> None:
        closed  = [t for t in self.trades if t["status"] == "closed"]
        open_tr = [t for t in self.trades if t["status"] == "open"]

        realized_pl = sum(t["profit_loss"] for t in closed)
        unrealized  = sum(((t.get("trail_stop") or t["target_price"]) -
                           t["entry_price"]) * t["units"] for t in open_tr)

        wins = [t for t in closed if t["profit_loss"] > 0]
        win_rate = len(wins) / len(closed) if closed else 0

        self.portfolio.update({
            "realized_pl":      realized_pl,
            "open_pl":          unrealized,
            "total_positions":  len(self.trades),
            "closed_positions": len(closed),
            "open_positions":   len(open_tr),
            "win_rate":         round(win_rate, 4)
        })

    # -------------------------- storage ----------------------------
    def _flush(self) -> None:
        with TRADE_FILE.open("w") as f:
            json.dump({"portfolio": self.portfolio,
                       "trades":    self.trades}, f, indent=4)

    @staticmethod
    def _new_portfolio() -> Dict:
        return {"budget": 0,
                "realized_pl": 0,
                "open_pl": 0,
                "total_positions": 0,
                "closed_positions": 0,
                "open_positions": 0,
                "win_rate": 0.0}
