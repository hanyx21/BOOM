#!/usr/bin/env python3
"""
Trend-Following Bot: Moving Average Crossover (Golden/Death Cross)

Features
- SMA crossover signals (configurable window lengths)
- Long-only by default; optional shorting
- Fixed-fraction position sizing
- Fixed % stop-loss and take-profit
- Backtest on CSV or yfinance
- Simple paper-trading loop using yfinance 1m/5m candles (simulated fills)
- Metrics + trade log + optional equity curve plot

Usage examples
--------------
# Backtest BTC-USD daily, 2019-01-01 to 2025-08-01
python mac_bot.py backtest --ticker BTC-USD --interval 1d --start 2019-01-01 --end 2025-08-01

# Backtest from a CSV (needs columns: timestamp,open,high,low,close,volume)
python mac_bot.py backtest --csv data.csv

# Paper-trade (simulated) BTC-USD on 5m candles
python mac_bot.py paper --ticker BTC-USD --interval 5m

Disclaimer: This code is for educational purposes only. Trading involves substantial risk.
"""

import argparse
import time
from dataclasses import dataclass
from typing import Optional, List, Tuple

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt


# ---------- Utilities ----------

def load_ohlcv_from_yf(ticker: str, interval: str, start: Optional[str] = None, end: Optional[str] = None) -> pd.DataFrame:
    """
    Load OHLCV using yfinance.
    interval examples: '1m','2m','5m','15m','1h','1d','1wk','1mo'
    """
    df = yf.download(ticker, interval=interval, start=start, end=end, auto_adjust=False, progress=False)
    if df.empty:
        raise ValueError("No data returned from yfinance. Check ticker/interval/time range.")
    df = df.rename(columns=str.lower)
    df.index.name = "timestamp"
    # Ensure numeric
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    return df[["open", "high", "low", "close", "volume"]]


def load_ohlcv_from_csv(csv_path: str, ts_col: str = "timestamp") -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    # Try parse timestamp
    df[ts_col] = pd.to_datetime(df[ts_col])
    df = df.set_index(ts_col).sort_index()
    cols = ["open", "high", "low", "close", "volume"]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing columns: {missing}. Required: {cols}")
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[cols].dropna()


def compute_indicators(df: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    out = df.copy()
    out[f"sma_{fast}"] = out["close"].rolling(fast).mean()
    out[f"sma_{slow}"] = out["close"].rolling(slow).mean()
    out["signal"] = 0
    # signal is computed on the CLOSE of each bar
    # +1 on golden cross, -1 on death cross
    cross_up = (out[f"sma_{fast}"].shift(1) <= out[f"sma_{slow}"].shift(1)) & (out[f"sma_{fast}"] > out[f"sma_{slow}"])
    cross_dn = (out[f"sma_{fast}"].shift(1) >= out[f"sma_{slow}"].shift(1)) & (out[f"sma_{fast}"] < out[f"sma_{slow}"])
    out.loc[cross_up, "signal"] = 1
    out.loc[cross_dn, "signal"] = -1
    return out


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: Optional[pd.Timestamp]
    side: str  # 'long' or 'short'
    entry_price: float
    exit_price: Optional[float]
    qty: float
    pnl: Optional[float]
    return_pct: Optional[float]


# ---------- Backtester ----------

class CrossoverBacktester:
    def __init__(
        self,
        fast: int = 50,
        slow: int = 200,
        initial_equity: float = 10_000.0,
        risk_fraction: float = 0.99,  # fraction of equity to allocate
        stop_loss_pct: float = 0.05,  # 5%
        take_profit_pct: float = 0.10,  # 10%
        allow_short: bool = False,
        fee_bps: float = 5.0  # 5 bps per trade side = 0.05%
    ):
        assert fast < slow, "fast SMA must be less than slow SMA"
        self.fast = fast
        self.slow = slow
        self.initial_equity = initial_equity
        self.risk_fraction = risk_fraction
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.allow_short = allow_short
        self.fee_bps = fee_bps / 10000.0

        self.equity_curve: List[float] = []
        self.trades: List[Trade] = []

    def run(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Trade]]:
        data = df.copy()
        data = compute_indicators(data, self.fast, self.slow)
        position = 0  # +1 long, -1 short, 0 flat
        entry_price = None
        qty = 0.0
        equity = self.initial_equity
        eq_series = []

        for ts, row in data.iterrows():
            price = float(row["close"])
            signal = int(row["signal"])
            sma_fast = row[f"sma_{self.fast}"]
            sma_slow = row[f"sma_{self.slow}"]

            # skip until MAs exist
            if np.isnan(sma_fast) or np.isnan(sma_slow):
                eq_series.append(equity)
                continue

            # manage open position (stop/take)
            if position != 0 and entry_price is not None and qty != 0:
                # hypothetical current value
                pnl_unrealized = (price - entry_price) * qty
                # Check stops
                if position > 0:
                    if price <= entry_price * (1 - self.stop_loss_pct) or price >= entry_price * (1 + self.take_profit_pct) or signal < 0:
                        # exit long
                        fee = price * abs(qty) * self.fee_bps
                        cash = price * qty - fee
                        equity += cash
                        ret_pct = (price - entry_price) / entry_price
                        self.trades.append(Trade(entry_time=entry_ts, exit_time=ts, side="long",
                                                 entry_price=entry_price, exit_price=price, qty=qty,
                                                 pnl=cash - (entry_price * qty), return_pct=ret_pct))
                        position = 0
                        entry_price = None
                        qty = 0.0
                else:
                    if price >= entry_price * (1 + self.stop_loss_pct) or price <= entry_price * (1 - self.take_profit_pct) or signal > 0:
                        # exit short
                        fee = price * abs(qty) * self.fee_bps
                        cash = -price * qty - fee  # closing short returns cash
                        equity += cash
                        ret_pct = (entry_price - price) / entry_price
                        self.trades.append(Trade(entry_time=entry_ts, exit_time=ts, side="short",
                                                 entry_price=entry_price, exit_price=price, qty=qty,
                                                 pnl=cash - (-entry_price * qty), return_pct=ret_pct))
                        position = 0
                        entry_price = None
                        qty = 0.0

            # consider new entries if flat
            if position == 0:
                if signal > 0:
                    # enter long
                    alloc = equity * self.risk_fraction
                    qty = (alloc / price)
                    fee = price * qty * self.fee_bps
                    equity -= (price * qty + fee)
                    position = 1
                    entry_price = price
                    entry_ts = ts
                elif signal < 0 and self.allow_short:
                    alloc = equity * self.risk_fraction
                    qty = (alloc / price)  # positive qty used; short position has negative cash at entry
                    fee = price * qty * self.fee_bps
                    equity -= fee  # borrow & sell gives cash; we keep equity bookkeeping by fees only here
                    position = -1
                    entry_price = price
                    entry_ts = ts

            eq_series.append(equity + (0 if position == 0 else (price - entry_price) * (qty if position > 0 else -qty)))

        data["equity"] = eq_series
        self.equity_curve = eq_series
        return data, self.trades

    # ---------- Metrics ----------

    @staticmethod
    def _sharpe(returns: pd.Series, periods_per_year: int) -> float:
        if returns.std() == 0 or returns.empty:
            return 0.0
        return (returns.mean() / returns.std()) * np.sqrt(periods_per_year)

    @staticmethod
    def _max_drawdown(equity: pd.Series) -> float:
        roll_max = equity.cummax()
        dd = equity / roll_max - 1.0
        return float(dd.min())

    def summarize(self, df_eq: pd.DataFrame, interval: str) -> dict:
        eq = df_eq["equity"].dropna()
        if eq.empty:
            return {}
        ret = eq.pct_change().dropna()
        total_return = eq.iloc[-1] / eq.iloc[0] - 1
        # infer periods per year
        mapping = {
            "1m": 365 * 24 * 60,
            "2m": 365 * 24 * 30,
            "5m": 365 * 24 * 12,
            "15m": 365 * 24 * 4,
            "30m": 365 * 24 * 2,
            "1h": 365 * 24,
            "1d": 252,      # trading days
            "1wk": 52,
            "1mo": 12,
        }
        ppy = mapping.get(interval, 252)
        years = max(1e-9, len(eq) / ppy)
        cagr = (1 + total_return) ** (1 / years) - 1
        sharpe = self._sharpe(ret, ppy)
        mdd = self._max_drawdown(eq)
        wins = [t for t in self.trades if t.pnl is not None and t.pnl > 0]
        win_rate = len(wins) / max(1, len(self.trades))
        return {
            "Total Return": f"{total_return*100:.2f}%",
            "CAGR": f"{cagr*100:.2f}%",
            "Sharpe (simple)": f"{sharpe:.2f}",
            "Max Drawdown": f"{mdd*100:.2f}%",
            "Trades": len(self.trades),
            "Win rate": f"{win_rate*100:.1f}%"
        }

    def plot(self, df_eq: pd.DataFrame, show: bool = True, save_path: Optional[str] = None):
        fig, ax = plt.subplots(figsize=(11, 6))
        (df_eq["equity"] / df_eq["equity"].iloc[0]).plot(ax=ax, label="Equity (normalized)")
        df_eq["close"].pct_change().add(1).cumprod().plot(ax=ax, alpha=0.6, label="Buy & Hold (normalized)")
        ax.set_title(f"SMA Crossover Backtest (fast={self.fast}, slow={self.slow})")
        ax.set_ylabel("Growth (x)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        if save_path:
            plt.savefig(save_path, dpi=140, bbox_inches="tight")
        if show:
            plt.show()
        plt.close(fig)


# ---------- Paper trading (simulated) ----------

def paper_trade_loop(
    ticker: str,
    interval: str = "5m",
    fast: int = 50,
    slow: int = 200,
    initial_equity: float = 10_000.0,
    risk_fraction: float = 0.99,
    stop_loss_pct: float = 0.05,
    take_profit_pct: float = 0.10,
    allow_short: bool = False,
    poll_seconds: int = 60
):
    """
    Simulates a live trading loop by polling recent data and applying the strategy
    at the close of each new bar. Uses the same execution logic as the backtester.
    """
    print(f"[paper] Starting simulated trading on {ticker} ({interval}). Ctrl+C to stop.")
    state_equity = initial_equity
    backtester = CrossoverBacktester(
        fast=fast, slow=slow, initial_equity=initial_equity,
        risk_fraction=risk_fraction, stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct, allow_short=allow_short
    )

    last_bar_time = None
    history = None

    try:
        while True:
            # Fetch enough history to compute SMAs
            lookback_bars = max(slow * 3, 500)
            hist = yf.download(ticker, interval=interval, period="60d", progress=False).rename(columns=str.lower)
            if hist.empty:
                print("[paper] No data fetched. Retrying...")
                time.sleep(poll_seconds)
                continue
            hist.index.name = "timestamp"
            hist = hist[["open", "high", "low", "close", "volume"]].dropna()
            if len(hist) < slow + 5:
                print("[paper] Not enough data yet. Retrying...")
                time.sleep(poll_seconds)
                continue
            hist = hist.tail(lookback_bars)

            # Only act when a new candle is finalized
            current_last = hist.index[-1]
            if last_bar_time is not None and current_last == last_bar_time:
                time.sleep(poll_seconds)
                continue
            last_bar_time = current_last

            # Run a one-pass "backtest" over history to get current position/equity
            df_eq, _ = backtester.run(hist)
            equity_now = df_eq["equity"].iloc[-1]
            last_price = float(hist["close"].iloc[-1])
            print(f"[paper] {current_last} price={last_price:.2f} equity={equity_now:.2f} trades={len(backtester.trades)}")

            # Sleep until next poll
            time.sleep(poll_seconds)

    except KeyboardInterrupt:
        print("\n[paper] Stopped by user.")


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(description="SMA Crossover Trend-Following Bot")
    sub = parser.add_subparsers(dest="mode", required=True)

    # Backtest
    p_back = sub.add_parser("backtest", help="Run a backtest")
    src = p_back.add_mutually_exclusive_group(required=True)
    src.add_argument("--ticker", type=str, help="yfinance ticker, e.g., BTC-USD, AAPL")
    src.add_argument("--csv", type=str, help="Path to CSV with columns timestamp,open,high,low,close,volume")

    p_back.add_argument("--interval", type=str, default="1d", help="yfinance interval (1m,5m,15m,1h,1d,1wk,1mo)")
    p_back.add_argument("--start", type=str, default=None, help="start date YYYY-MM-DD")
    p_back.add_argument("--end", type=str, default=None, help="end date YYYY-MM-DD")
    p_back.add_argument("--fast", type=int, default=50)
    p_back.add_argument("--slow", type=int, default=200)
    p_back.add_argument("--equity", type=float, default=10_000.0)
    p_back.add_argument("--risk-fraction", type=float, default=0.99)
    p_back.add_argument("--stop-loss", type=float, default=0.05)
    p_back.add_argument("--take-profit", type=float, default=0.10)
    p_back.add_argument("--allow-short", action="store_true")
    p_back.add_argument("--fee-bps", type=float, default=5.0)
    p_back.add_argument("--plot", action="store_true")
    p_back.add_argument("--save-plot", type=str, default=None)

    # Paper-trading (simulated)
    p_paper = sub.add_parser("paper", help="Simulated live trading")
    p_paper.add_argument("--ticker", type=str, required=True)
    p_paper.add_argument("--interval", type=str, default="5m")
    p_paper.add_argument("--fast", type=int, default=50)
    p_paper.add_argument("--slow", type=int, default=200)
    p_paper.add_argument("--equity", type=float, default=10_000.0)
    p_paper.add_argument("--risk-fraction", type=float, default=0.99)
    p_paper.add_argument("--stop-loss", type=float, default=0.05)
    p_paper.add_argument("--take-profit", type=float, default=0.10)
    p_paper.add_argument("--allow-short", action="store_true")
    p_paper.add_argument("--poll-seconds", type=int, default=60)

    args = parser.parse_args()

    if args.mode == "backtest":
        # Load data
        if args.csv:
            df = load_ohlcv_from_csv(args.csv)
            interval = "1d"  # unknown; used only for annualization—adjust if you know it
        else:
            df = load_ohlcv_from_yf(args.ticker, args.interval, start=args.start, end=args.end)
            interval = args.interval

        bt = CrossoverBacktester(
            fast=args.fast, slow=args.slow, initial_equity=args.equity,
            risk_fraction=args.risk_fraction, stop_loss_pct=args.stop_loss,
            take_profit_pct=args.take_profit, allow_short=args.allow_short,
            fee_bps=args.fee_bps
        )
        df_eq, trades = bt.run(df)
        stats = bt.summarize(df_eq, interval)
        # Print summary
        print("\n=== Backtest Summary ===")
        for k, v in stats.items():
            print(f"{k:16s} : {v}")
        print(f"Trades               : {len(trades)}")
        # Trade log
        if trades:
            tl = pd.DataFrame([{
                "entry_time": t.entry_time, "exit_time": t.exit_time, "side": t.side,
                "entry_price": t.entry_price, "exit_price": t.exit_price,
                "qty": t.qty, "pnl": t.pnl, "return_pct": t.return_pct
            } for t in trades])
            print("\n--- Trade Log (last 10) ---")
            print(tl.tail(10).to_string(index=False))
        # Plot
        if args.plot or args.save_plot:
            bt.plot(df_eq, show=args.plot, save_path=args.save_plot)

    elif args.mode == "paper":
        paper_trade_loop(
            ticker=args.ticker, interval=args.interval, fast=args.fast, slow=args.slow,
            initial_equity=args.equity, risk_fraction=args.risk_fraction,
            stop_loss_pct=args.stop_profit if hasattr(args, "stop_profit") else 0.05,
            take_profit_pct=args.take_profit, allow_short=args.allow_short,
            poll_seconds=args.poll_seconds
        )


if __name__ == "__main__":
    main()
