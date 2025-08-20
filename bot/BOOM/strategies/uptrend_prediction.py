# """uptrend_following.py
# ====================================================
# Fast‑scalp up‑trend scorer for +0.20 % targets
# ----------------------------------------------------
# * Replaces / complements the original `uptrend_prediction.py`.
# * Same public API:  `predict_uptrend(pair) -> int  # 0‑100 score`.
# * Designed for alt‑coin scalping: return a score **before** the
#   first +0.20 % burst so `main.py` can open the trade in time.
#
# Key upgrades vs the old logic
# -----------------------------
# 1. **Dual time‑frame data**
#    • 5‑minute candles  – trend & ATR calculations (faster EMA 9/21/100).
#    • 1‑minute candles – micro‑impulse trigger (+0.05 % last 60 s).
#
# 2. **Adaptive breakout**
#    price > recent‑high + `max(0.0015, 0.25 × ATR)`  *(0.15 % floor)*.
#
# 3. **Liquidity guard**
#    15‑bar quote‑volume ≥ 300 k USDT → filters out illiquid dust pairs.
#
# 4. **Soft scoring**
#    Near‑misses earn partial credit instead of 0.  (Linear ramps.)
#
# 5. **Hard risk/reward + stop‑loss helpers**
#    Target ≤ 1.2 × ATR  ⇒ TP = +0.20 %, suggested SL = max(0.25 %, 0.8×ATR).
#
# The weight table still sums to 100 so `main.py` needs **no change**.
# """
#
# from __future__ import annotations
#
# import numpy as np
# import pandas as pd
# import ccxt
# from utils.data_ingestion import fetch_crypto_data
# from config.configs import TARGET_PERCENTAGE
#
# BINANCE = ccxt.binance()
#
# # ──────────────────────────── indicator helpers ──────────────────────────────
#
# def _ema(s: pd.Series, span: int) -> pd.Series:
#     return s.ewm(span=span, adjust=False).mean()
#
# def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
#     d = s.diff()
#     gain = d.clip(lower=0).rolling(n).mean()
#     loss = (-d.clip(upper=0)).rolling(n).mean()
#     rs = gain / loss.replace(0, np.nan)
#     return 100 - 100 / (1 + rs)
#
# def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
#     tr = pd.concat([
#         (df['high'] - df['low']).abs(),
#         (df['high'] - df['close'].shift()).abs(),
#         (df['low'] - df['close'].shift()).abs()
#     ], axis=1).max(axis=1)
#     return tr.rolling(n).mean()
#
# def _adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
#     up = df['high'].diff()
#     dn = -df['low'].diff()
#     plus = np.where((up > dn) & (up > 0), up, 0.0)
#     minus = np.where((dn > up) & (dn > 0), dn, 0.0)
#     atr = _atr(df, n)
#     plus_di = 100 * pd.Series(plus).rolling(n).sum() / atr
#     minus_di = 100 * pd.Series(minus).rolling(n).sum() / atr
#     dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
#     return dx.rolling(n).mean()
#
# # ───────────────────────────── utility functions ─────────────────────────────
#
# def _target_price(price: float) -> float:
#     """Return price +0.20 % (using global TARGET_PERCENTAGE)."""
#     return price * (1 + TARGET_PERCENTAGE / 100)
#
# # soft‑grade helpers -----------------------------------------------------------
#
# def _linear_score(value: float, lo: float, hi: float) -> float:
#     """0 if ≤ lo, 1 if ≥ hi, linearly scaled in‑between."""
#     if value <= lo:
#         return 0.0
#     if value >= hi:
#         return 1.0
#     return (value - lo) / (hi - lo)
#
# # ───────────────────────────── scoring weights ────────────────────────────────
# WEIGHTS = {
#     "breakout": 18,
#     "ema":       15,
#     "rsi":       12,
#     "adx":       12,
#     "macd":      12,
#     "volume":     8,
#     "impulse":   13,
#     "rr":        10,
# }  # sums to 100
#
# # ───────────────────────── core scoring routine ──────────────────────────────
#
# def score_uptrend(pair: str) -> int:
#     """Return 0‑100 strength score for a +0.20 % scalp opportunity."""
#
#     # -------- data fetch ------------------------------------------------------
#     df5 = fetch_crypto_data(pair, timeframe='5m', limit=300)  # 25 h
#     df1 = pd.DataFrame(BINANCE.fetch_ohlcv(pair, '1m', limit=3),
#                        columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
#
#     close5 = df5['close']
#     cur = close5.iloc[-1]
#
#     # -------- liquidity check -------------------------------------------------
#     quote_vol_15 = (df5['close'][-15:] * df5['volume'][-15:]).sum()
#     if quote_vol_15 < 300_000:
#         print(f"{pair}: skipped – illiquid ({quote_vol_15/1e3:.1f} k USDT last 15 m)")
#         return 0
#
#     # -------- indicators (5‑minute) ------------------------------------------
#     recent_high = close5.rolling(40).max().iloc[-2]
#     atr = _atr(df5).iloc[-1]
#     ema9, ema21, ema100 = _ema(close5, 9).iloc[-1], _ema(close5, 21).iloc[-1], _ema(close5, 100).iloc[-1]
#     rsi = _rsi(close5).iloc[-1]
#     adx = _adx(df5).iloc[-1]
#
#     macd_fast = _ema(close5, 12)
#     macd_slow = _ema(close5, 26)
#     macd_hist = (macd_fast - macd_slow) - _ema(macd_fast - macd_slow, 9)
#     macd_up = macd_hist.iloc[-1] > macd_hist.iloc[-2]
#
#     vol_spike = df5['volume'].iloc[-1] > 1.3 * df5['volume'].rolling(20).mean().iloc[-1]
#
#     # -------- micro impulse (1‑minute) ---------------------------------------
#     impulse_pct = (df1['close'].iloc[-1] - df1['open'].iloc[-1]) / df1['open'].iloc[-1] * 100
#     impulse_ok = impulse_pct >= 0.05
#
#     # -------- breakout & RR rules --------------------------------------------
#     breakout_ok = cur > recent_high + max(0.0015 * cur, 0.25 * atr)  # 0.15 % or 0.25×ATR
#     rr_ok = _target_price(cur) - cur <= 1.2 * atr
#
#     # -------- assemble soft scores ------------------------------------------
#     parts: dict[str, float] = {
#         'breakout': 1.0 if breakout_ok else 0.0,
#         'ema':      1.0 if ema9 > ema21 > ema100 else 0.0,
#         'rsi':      _linear_score(rsi, 50, 65),
#         'adx':      _linear_score(adx, 20, 28),
#         'macd':     1.0 if macd_up else 0.0,
#         'volume':   _linear_score(df5['volume'].iloc[-1] / df5['volume'].rolling(20).mean().iloc[-1], 1.0, 2.0),
#         'impulse':  1.0 if impulse_ok else 0.0,
#         'rr':       1.0 if rr_ok else 0.0,
#     }
#
#     score = round(sum(WEIGHTS[k] * parts[k] for k in WEIGHTS))
#
#     # -------- debug -----------------------------------------------------------
#     print(
#         f"SCORE {pair}: {score}/100  ―  "
#         f"impulse={impulse_pct:+.3f}%  ATR={atr/cur*100:.2f}%  "
#         f"{ {k: round(parts[k],2) for k in parts} }"
#     )
#
#     return score
#
# # ───────────────────────── external API wrapper ──────────────────────────────
#
# def predict_uptrend(pair: str) -> int:
#     """Public entry: fetch, score, return 0‑100 integer."""
#     try:
#         return score_uptrend(pair)
#     except Exception as e:
#         print(f"{pair}: scoring error → {e}")
#         return 0
#
# # ─────────────────────────── quick manual test ───────────────────────────────
# if __name__ == "__main__":
#     print(predict_uptrend('BTC/USDT'))

# strategies/uptrend_following.py
"""
Fast-scalp up-trend scorer for +0.20 % targets
----------------------------------------------------
* Replaces / complements the original `uptrend_prediction.py`.
* Same public API:  `predict_uptrend(pair) -> int  # 0-100 score`.
* Designed for alt-coin scalping: return a score BEFORE the
  first +0.20 % burst so `main.py` can open the trade in time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import ccxt
from utils.data_ingestion import fetch_crypto_data
from config.configs import TARGET_PERCENTAGE

# NEW: automatic resistance detector / channel fitter
from utils.auto_levels import near_resistance_veto

BINANCE = ccxt.binance()

# ──────────────────────────── indicator helpers ──────────────────────────────

def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()

def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    gain = d.clip(lower=0).rolling(n).mean()
    loss = (-d.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    tr = pd.concat([
        (df['high'] - df['low']).abs(),
        (df['high'] - df['close'].shift()).abs(),
        (df['low'] - df['close'].shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def _adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df['high'].diff()
    dn = -df['low'].diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr = _atr(df, n)
    plus_di = 100 * pd.Series(plus).rolling(n).sum() / atr
    minus_di = 100 * pd.Series(minus).rolling(n).sum() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return dx.rolling(n).mean()

# ───────────────────────────── utility functions ─────────────────────────────

def _target_price(price: float) -> float:
    """Return price +0.20 % (using global TARGET_PERCENTAGE)."""
    return price * (1 + TARGET_PERCENTAGE / 100)

def _linear_score(value: float, lo: float, hi: float) -> float:
    """0 if ≤ lo, 1 if ≥ hi, linearly scaled in-between."""
    if value <= lo:
        return 0.0
    if value >= hi:
        return 1.0
    return (value - lo) / (hi - lo)

# ───────────────────────────── scoring weights ────────────────────────────────
WEIGHTS = {
    "breakout": 18,
    "ema":       15,
    "rsi":       12,
    "adx":       12,
    "macd":      12,
    "volume":     8,
    "impulse":   13,
    "rr":        10,
}  # sums to 100

# ───────────────────────── core scoring routine ──────────────────────────────

def score_uptrend(pair: str) -> int:
    """Return 0-100 strength score for a +0.20 % scalp opportunity."""

    # -------- data fetch ------------------------------------------------------
    df5 = fetch_crypto_data(pair, timeframe='5m', limit=300)  # ~25 h
    df1 = pd.DataFrame(BINANCE.fetch_ohlcv(pair, '1m', limit=3),
                       columns=['ts', 'open', 'high', 'low', 'close', 'volume'])

    close5 = df5['close']
    cur = float(close5.iloc[-1])

    # -------- liquidity check -------------------------------------------------
    quote_vol_15 = float((df5['close'][-15:] * df5['volume'][-15:]).sum())
    if quote_vol_15 < 300_000:
        print(f"{pair}: skipped – illiquid ({quote_vol_15/1e3:.1f} k USDT last 15 m)")
        return 0

    # -------- indicators (5-minute) ------------------------------------------
    recent_high = float(close5.rolling(40).max().iloc[-2])  # uses closes
    atr = float(_atr(df5).iloc[-1])
    ema9, ema21, ema100 = float(_ema(close5, 9).iloc[-1]), float(_ema(close5, 21).iloc[-1]), float(_ema(close5, 100).iloc[-1])
    rsi = float(_rsi(close5).iloc[-1])
    adx = float(_adx(df5).iloc[-1])

    macd_fast = _ema(close5, 12)
    macd_slow = _ema(close5, 26)
    macd_hist = (macd_fast - macd_slow) - _ema(macd_fast - macd_slow, 9)
    macd_up = bool(macd_hist.iloc[-1] > macd_hist.iloc[-2])

    vol_spike = bool(df5['volume'].iloc[-1] > 1.3 * df5['volume'].rolling(20).mean().iloc[-1])

    # -------- auto resistances & veto ----------------------------------------
    # -------- auto resistances & veto ----------------------------------------
    should_skip, rctx = near_resistance_veto(df5, cur_price=cur, atr_value=atr)

    # Pretty diagnostics about resistances
    d_horiz = rctx["d_horiz"]
    d_chan = rctx["d_chan"]
    nearest_is_channel = d_chan <= d_horiz
    nearest_line_val = rctx["upper_now"] if nearest_is_channel else (
        rctx["h_levels"][0] if rctx["h_levels"] else float("nan"))
    gap_price = min(d_horiz, d_chan)
    gap_pct = (gap_price / cur) * 100.0
    buf_pct = (rctx["buffer"] / cur) * 100.0

    # Short list of horizontal levels for context (max 3)
    levels_preview = ", ".join(f"{lv:.8g}" for lv in rctx["h_levels"][:3]) or "-"

    print(
        f"RESIST {pair}: near={rctx['near_resistance']}  "
        f"gap={gap_price:.8g} ({gap_pct:.3f}%)  buffer={rctx['buffer']:.8g} ({buf_pct:.3f}%)  "
        f"nearest={'channel_top' if nearest_is_channel else 'horiz'}@{nearest_line_val:.8g}  "
        f"upper_ch={rctx['upper_now']:.8g}  levels=[{levels_preview}]"
    )

    if should_skip:
        print(
            f"{pair}: skipped – near resistance "
            f"(d_horiz={d_horiz:.8g}, d_chan={d_chan:.8g}, upper_now={rctx['upper_now']:.8g})"
        )
        return 0

    # -------- micro impulse (1-minute) ---------------------------------------
    impulse_pct = float((df1['close'].iloc[-1] - df1['open'].iloc[-1]) / df1['open'].iloc[-1] * 100.0)
    impulse_ok = impulse_pct >= 0.05

    # -------- breakout & RR rules --------------------------------------------
    breakout_ok = cur > (recent_high + max(0.0015 * cur, 0.25 * atr))  # 0.15 % or 0.25×ATR
    rr_ok = (_target_price(cur) - cur) <= 1.2 * atr

    # -------- assemble soft scores ------------------------------------------
    parts: dict[str, float] = {
        'breakout': 1.0 if breakout_ok else 0.0,
        'ema':      1.0 if (ema9 > ema21 > ema100) else 0.0,
        'rsi':      _linear_score(rsi, 50, 65),
        'adx':      _linear_score(adx, 20, 28),
        'macd':     1.0 if macd_up else 0.0,
        'volume':   _linear_score(
                        float(df5['volume'].iloc[-1] / df5['volume'].rolling(20).mean().iloc[-1]),
                        1.0, 2.0
                    ),
        'impulse':  1.0 if impulse_ok else 0.0,
        'rr':       1.0 if rr_ok else 0.0,
    }

    score = int(round(sum(WEIGHTS[k] * parts[k] for k in WEIGHTS)))

    # -------- debug -----------------------------------------------------------
    print(
        f"SCORE {pair}: {score}/100  —  "
        f"impulse={impulse_pct:+.3f}%  ATR={atr/cur*100:.2f}%  "
        f"{ {k: round(parts[k], 2) for k in parts} }"
    )

    return score

# ───────────────────────── external API wrapper ──────────────────────────────

def predict_uptrend(pair: str) -> int:
    """Public entry: fetch, score, return 0-100 integer."""
    try:
        return score_uptrend(pair)
    except Exception as e:
        print(f"{pair}: scoring error → {e}")
        return 0

# ─────────────────────────── quick manual test ───────────────────────────────
if __name__ == "__main__":
    print(predict_uptrend('BTC/USDT'))
