#
# import winsound
# import json
# import os
#
# class FakeExecution:
#     def __init__(self, initial_balance):
#         self.balance = initial_balance
#         self.trades = []
#         self.trade_file = 'trade_log.json'
#         if os.path.exists(self.trade_file):
#             with open(self.trade_file, 'r') as file:
#                 self.trades = json.load(file)
#         else:
#             with open(self.trade_file, 'w') as file:
#                 json.dump(self.trades, file)
#
#     def execute_trade(self, action, symbol, amount, price):
#         """Simulate executing a trade."""
#         trade = {
#             'symbol': symbol,
#             'action': action,
#             'amount': amount,
#             'price': price,
#             'target_price': self.calculate_target_price(price),
#             'entry_price': price,
#             'status': 'open',
#             'target_reached': False,
#             'target_reached_price': None,
#             'profit_loss': 0
#         }
#         self.trades.append(trade)
#         self.save_trades()
#
#     def save_trades(self):
#         """Save trades to a JSON file."""
#         with open(self.trade_file, 'w') as file:
#             json.dump(self.trades, file, indent=4)
#
#     def calculate_target_price(self, entry_price):
#         """Calculate target price based on 0.2% gain."""
#         return entry_price * 1.002  # Target is 0.2% higher
#
#     def track_positions(self, current_prices):
#         """Track positions and check if target price is reached."""
#         all_closed = True  # Assume all positions are closed initially
#         for trade in self.trades:
#             if trade['status'] == 'open':
#                 symbol = trade['symbol']
#                 target_price = trade['target_price']
#                 current_price = current_prices.get(symbol)
#
#                 # Check if current price is equal to or exceeds target price
#                 if current_price >= target_price:
#                     trade['status'] = 'closed'
#                     trade['target_reached'] = True
#                     trade['target_reached_price'] = current_price
#                     trade['profit_loss'] = current_price - trade['entry_price']
#
#                     # Play the Windows default beep sound when target is reached
#                     winsound.Beep(1000, 500)  # Frequency: 1000Hz, Duration: 500ms
#
#                     print(f"Target reached for {symbol}: {current_price}. Profit/Loss: {trade['profit_loss']}")
#                     self.save_trades()
#                 else:
#                     all_closed = False  # If any position is still open, don't assume all are closed
#
#         return all_closed  # Return True only if all positions are closed
#
#     def has_open_positions(self) -> bool:
#         """True if there is at least one open position."""
#         return any(t['status'] == 'open' for t in self.trades)
#
#     def get_open_positions(self):
#         """Return all open positions."""
#         return [trade for trade in self.trades if trade['status'] == 'open']
#
######################################################################################
# import winsound, json, os
# from pathlib import Path
# from typing import Dict, List
# import time
# TRADE_FILE = Path("trade_log.json")
# MAX_HOLD_SEC = 300  # 5 minutes
#
# class FakeExecution:
#     # ---------- unchanged __init__ ----------------------------------
#     def __init__(self, initial_balance):
#         self.balance = initial_balance
#
#         if TRADE_FILE.exists():
#             with TRADE_FILE.open() as f:
#                 store = json.load(f)
#             self.trades: List[Dict] = store.get("trades", [])
#             self.portfolio: Dict    = store.get("portfolio", self._new_portfolio())
#         else:
#             self.trades    = []
#             self.portfolio = self._new_portfolio()
#             self._flush()
#
#     def has_open_positions(self) -> bool:
#         """True if at least one trade is still open."""
#         return any(t["status"] == "open" for t in self.trades)
#
#     # ---------- public API ------------------------------------------
#     # def execute_trade(self, action, symbol, amount_usdt, price):
#     #     units = amount_usdt / price  # how many coins can be bought
#     #     trade = {
#     #         "symbol": symbol,
#     #         "action": action,
#     #
#     #         "amount_usdt": amount_usdt,  # money you put in
#     #         "units": units,  # actual coin size
#     #
#     #         "entry_price": price,
#     #         "target_price": self.calculate_target_price(price),
#     #
#     #         "status": "open",
#     #         "target_reached": False,
#     #         "target_reached_price": None,
#     #         "profit_loss": 0
#     #     }
#     #     self.trades.append(trade)
#     #     self._update_portfolio()
#     #     self._flush()
#     # utils/execution.py  – inside execute_trade()
#     import time  # add near other imports
#
#     def execute_trade(self, action, symbol, amount_usdt, price):
#         units = amount_usdt / price  # ← already using USDT stake
#         trade = {
#             "symbol": symbol,
#             "action": action,
#             "amount_usdt": amount_usdt,
#             "units": units,
#             "entry_price": price,
#             "target_price": self.calculate_target_price(price),
#             "status": "open",
#             "target_reached": False,
#             "target_reached_price": None,
#             "profit_loss": 0,
#             "open_time": time.time()  # ← NEW
#         }
#         self.trades.append(trade)
#         self._update_portfolio()
#         self._flush()
#
#
#     # def track_positions(self, current_prices):
#     #     all_closed = True
#     #     for t in self.trades:
#     #         if t["status"] == "open":
#     #
#     #             cur = current_prices.get(t["symbol"])
#     #             if cur >= t["target_price"]:
#     #
#     #
#     #
#     #                 t["status"] = "closed"
#     #                 t["target_reached"] = True
#     #                 t["target_reached_price"] = cur
#     #
#     #                 spread = cur - t["entry_price"]  # per-coin gain
#     #                 t["profit_loss"] = spread * t["units"]  # ← profit in USDT
#     #                 winsound.Beep(1000, 300)
#     #             else:
#     #                 all_closed = False
#     #     self._update_portfolio()
#     #     self._flush()
#     #     return all_closed
#
#
#     def track_positions(self, current_prices):
#         all_closed = True
#         now = time.time()
#
#         for t in self.trades:
#             if t["status"] != "open":
#                 continue
#
#             sym = t["symbol"]
#             cur = current_prices.get(sym)
#             targ = t["target_price"]
#
#             # --- original target hit ---------------------------------
#             if cur >= targ:
#                 self._close_trade(t, cur, "target hit")
#                 continue
#
#             # --- NEW: time stop --------------------------------------
#             held = now - t["open_time"]
#             if held >= MAX_HOLD_SEC and cur >= t["entry_price"]:
#                 self._close_trade(t, cur, "5-min breakeven exit")
#                 continue
#
#             all_closed = False
#
#         self._update_portfolio()
#         self._flush()
#         return all_closed
#
#     def _close_trade(self, trade: dict, exit_price: float, reason: str) -> None:
#         trade["status"] = "closed"
#         trade["target_reached"] = (reason == "target hit")
#         trade["target_reached_price"] = exit_price
#
#         spread = exit_price - trade["entry_price"]
#         profit = spread * trade["units"]
#
#         trade["profit_loss"] = profit
#
#         # ----- new percentage fields --------------------------------
#         trade["pct_move"] = round(spread / trade["entry_price"] * 100, 3)  # price change %
#         trade["pct_gain"] = round(profit / trade["amount_usdt"] * 100, 3)  # wallet gain %
#         # -------------------------------------------------------------
#
#         print(f"Close {trade['symbol']} @ {exit_price:.6f}  ({reason})"
#               f"  +{trade['pct_move']}%  {profit:.4f} USDT")
#         winsound.Beep(1000, 300)
#
#     def recently_traded(self, symbol: str, cooldown_sec: int = 3600) -> bool:
#         """
#         True if this symbol was opened less than <cooldown_sec> ago.
#         Looks at the most recent occurrence of the symbol in the log.
#         """
#         now = time.time()
#         for t in reversed(self.trades):  # newest first → early exit
#             if t["symbol"] == symbol:
#                 return (now - t["open_time"]) < cooldown_sec
#         return False
#
#     def get_open_positions(self):
#         return [t for t in self.trades if t["status"] == "open"]
#
#     # ---------- helpers ---------------------------------------------
#     def calculate_target_price(self, price):
#         return price * 1.002
#
#     def _new_portfolio(self):
#         return {"budget": self.balance, "realized_pl": 0, "open_pl": 0,
#                 "total_positions": 0, "closed_positions": 0,
#                 "open_positions": 0, "win_rate": 0}
#
#     def _update_portfolio(self):
#         closed = [t for t in self.trades if t["status"] == "closed"]
#         open_tr = [t for t in self.trades if t["status"] == "open"]
#
#         realized = sum(t["profit_loss"] for t in closed)
#
#         # use UNITS, not amount_usdt / amount
#         open_pl = sum((t["target_price"] - t["entry_price"]) * t["units"]
#                       for t in open_tr)
#
#         wins = [t for t in closed if t["profit_loss"] > 0]
#         win_rate = len(wins) / len(closed) if closed else 0
#
#         self.portfolio.update({
#             "realized_pl": realized,
#             "open_pl": open_pl,
#             "total_positions": len(self.trades),
#             "closed_positions": len(closed),
#             "open_positions": len(open_tr),
#             "win_rate": round(win_rate, 4)
#         })
#
#     def _flush(self):
#         with TRADE_FILE.open("w") as f:
#             json.dump({"portfolio": self.portfolio, "trades": self.trades}, f, indent=4)
##########################################

import winsound, json, os
from pathlib import Path
from typing import Dict, List
import time
TRADE_FILE = Path("trade_log.json")
MAX_HOLD_SEC = 300  # 5 minutes

class FakeExecution:
    # ---------- unchanged __init__ ----------------------------------
    def __init__(self, initial_balance):
        self.balance = initial_balance

        if TRADE_FILE.exists():
            with TRADE_FILE.open() as f:
                store = json.load(f)
            self.trades: List[Dict] = store.get("trades", [])
            self.portfolio: Dict    = store.get("portfolio", self._new_portfolio())
        else:
            self.trades    = []
            self.portfolio = self._new_portfolio()
            self._flush()

    def has_open_positions(self) -> bool:
        """True if at least one trade is still open."""
        return any(t["status"] == "open" for t in self.trades)

    # ---------- public API ------------------------------------------
    # def execute_trade(self, action, symbol, amount_usdt, price):
    #     units = amount_usdt / price  # how many coins can be bought
    #     trade = {
    #         "symbol": symbol,
    #         "action": action,
    #
    #         "amount_usdt": amount_usdt,  # money you put in
    #         "units": units,  # actual coin size
    #
    #         "entry_price": price,
    #         "target_price": self.calculate_target_price(price),
    #
    #         "status": "open",
    #         "target_reached": False,
    #         "target_reached_price": None,
    #         "profit_loss": 0
    #     }
    #     self.trades.append(trade)
    #     self._update_portfolio()
    #     self._flush()
    # utils/execution.py  – inside execute_trade()
    import time  # add near other imports

    def execute_trade(self, action, symbol, amount_usdt, price):
        units = amount_usdt / price  # ← already using USDT stake
        trade = {
            "symbol": symbol,
            "action": action,
            "amount_usdt": amount_usdt,
            "units": units,
            "entry_price": price,
            "target_price": self.calculate_target_price(price),
            "status": "open",
            "target_reached": False,
            "target_reached_price": None,
            "profit_loss": 0,
            "open_time": time.time()  # ← NEW
        }
        self.trades.append(trade)
        self._update_portfolio()
        self._flush()


    # def track_positions(self, current_prices):
    #     all_closed = True
    #     for t in self.trades:
    #         if t["status"] == "open":
    #
    #             cur = current_prices.get(t["symbol"])
    #             if cur >= t["target_price"]:
    #
    #
    #
    #                 t["status"] = "closed"
    #                 t["target_reached"] = True
    #                 t["target_reached_price"] = cur
    #
    #                 spread = cur - t["entry_price"]  # per-coin gain
    #                 t["profit_loss"] = spread * t["units"]  # ← profit in USDT
    #                 winsound.Beep(1000, 300)
    #             else:
    #                 all_closed = False
    #     self._update_portfolio()
    #     self._flush()
    #     return all_closed


    def track_positions(self, current_prices):
        all_closed = True
        now = time.time()

        for t in self.trades:
            if t["status"] != "open":
                continue

            sym = t["symbol"]
            cur = current_prices.get(sym)
            targ = t["target_price"]

            # --- original target hit ---------------------------------
            if cur >= targ:
                self._close_trade(t, cur, "target hit")
                continue

            # --- NEW: time stop --------------------------------------
            held = now - t["open_time"]
            if held >= MAX_HOLD_SEC and cur >= t["entry_price"]:
                self._close_trade(t, cur, "5-min breakeven exit")
                continue

            all_closed = False

        self._update_portfolio()
        self._flush()
        return all_closed

    def _close_trade(self, trade: dict, exit_price: float, reason: str) -> None:
        trade["status"] = "closed"
        trade["target_reached"] = (reason == "target hit")
        trade["target_reached_price"] = exit_price

        spread = exit_price - trade["entry_price"]
        profit = spread * trade["units"]

        trade["profit_loss"] = profit

        # ----- new percentage fields --------------------------------
        trade["pct_move"] = round(spread / trade["entry_price"] * 100, 3)  # price change %
        trade["pct_gain"] = round(profit / trade["amount_usdt"] * 100, 3)  # wallet gain %
        # -------------------------------------------------------------

        print(f"Close {trade['symbol']} @ {exit_price:.6f}  ({reason})"
              f"  +{trade['pct_move']}%  {profit:.4f} USDT")
        winsound.Beep(1000, 300)

    def recently_traded(self, symbol: str, cooldown_sec: int = 3600) -> bool:
        """
        True if this symbol was opened less than <cooldown_sec> ago.
        Looks at the most recent occurrence of the symbol in the log.
        """
        now = time.time()
        for t in reversed(self.trades):  # newest first → early exit
            if t["symbol"] == symbol:
                return (now - t["open_time"]) < cooldown_sec
        return False

    def get_open_positions(self):
        return [t for t in self.trades if t["status"] == "open"]

    # ---------- helpers ---------------------------------------------
    def calculate_target_price(self, price):
        return price * 1.002

    def _new_portfolio(self):
        return {"budget": self.balance, "realized_pl": 0, "open_pl": 0,
                "total_positions": 0, "closed_positions": 0,
                "open_positions": 0, "win_rate": 0}

    def _update_portfolio(self):
        closed = [t for t in self.trades if t["status"] == "closed"]
        open_tr = [t for t in self.trades if t["status"] == "open"]

        realized = sum(t["profit_loss"] for t in closed)

        # use UNITS, not amount_usdt / amount
        open_pl = sum((t["target_price"] - t["entry_price"]) * t["units"]
                      for t in open_tr)

        wins = [t for t in closed if t["profit_loss"] > 0]
        win_rate = len(wins) / len(closed) if closed else 0

        self.portfolio.update({
            "realized_pl": realized,
            "open_pl": open_pl,
            "total_positions": len(self.trades),
            "closed_positions": len(closed),
            "open_positions": len(open_tr),
            "win_rate": round(win_rate, 4)
        })

    def _flush(self):
        with TRADE_FILE.open("w") as f:
            json.dump({"portfolio": self.portfolio, "trades": self.trades}, f, indent=4)
