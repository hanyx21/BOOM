#
# import pandas as pd
# from utils.data_ingestion import fetch_crypto_data
# from config.configs import TARGET_PERCENTAGE
#
#
# def calculate_target_price(current_price, percentage):
#     """Calculate target price based on the percentage increase."""
#     return current_price * (1 + percentage / 100)
#
#
# def get_local_high(data: pd.DataFrame, window: int = 20):
#     """Get the highest price from the last 'window' periods."""
#     return data['close'].rolling(window=window).max().iloc[-1]
#
#
# def check_uptrend(data: pd.DataFrame) -> bool:
#     """Check if the crypto pair is in an uptrend using price action and momentum."""
#
#     # Calculate EMA (Exponential Moving Average) for short-term trend
#     ema10 = data['close'].ewm(span=10).mean().iloc[-1]
#     ema50 = data['close'].ewm(span=50).mean().iloc[-1]
#
#     # Calculate RSI (Relative Strength Index)
#     delta = data['close'].diff()
#     gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
#     loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
#     rs = gain / loss
#     rsi = 100 - (100 / (1 + rs))
#
#     # Get recent high and check the current price
#     recent_high = get_local_high(data, window=20)
#     current_price = data['close'].iloc[-1]
#
#     # Calculate the volatility range
#     price_range = data['high'] - data['low']
#     average_range = price_range.rolling(window=20).mean().iloc[-1]
#
#     # Debugging: Print values for analysis
#     print(f"EMA10: {ema10}, EMA50: {ema50}")
#     print(f"Recent High: {recent_high}, Current Price: {current_price}")
#     print(f"RSI: {rsi.iloc[-1]}, Average Range: {average_range}")
#
#     # **Relaxed Breakout Condition**: Allow price within 0.5% of the recent high
#     if current_price > (recent_high * 0.995) and ema10 > ema50 and rsi.iloc[-1] > rsi.iloc[-2]:
#         print("Breakout detected with momentum confirmation.")
#         return True
#
#     # Additional check for volatility breakout
#     if price_range.iloc[-1] > average_range:
#         print("Volatility breakout detected.")
#         return True
#
#     return False
#
#
# def predict_uptrend(pair: str) -> bool:
#     """Predict a potential 0.2% price increase based on current trends."""
#     data = fetch_crypto_data(pair)  # Fetch real-time data
#     current_price = data['close'].iloc[-1]
#     target_price = calculate_target_price(current_price, TARGET_PERCENTAGE)
#
#     # Debugging: Print current price and target price
#     print(f"Current price for {pair}: {current_price}")
#     print(f"Target price for {pair} (+0.2%): {target_price}")
#
#     # Check if uptrend is detected and price is below target
#     if check_uptrend(data) and current_price < target_price:
#         print(f"Uptrend detected for {pair}. Target price: {target_price}")
#         return True
#     print(f"No uptrend detected for {pair}.")
#     return False

################################################################################################################

# import pandas as pd
# from utils.data_ingestion import fetch_crypto_data
# from config.configs import TARGET_PERCENTAGE  # set to 2.0 now
# import numpy as np
#
#
# # ------------------------------------------------------------------
# def _ema(series: pd.Series, span: int) -> pd.Series:
#     return series.ewm(span=span, adjust=False).mean()
#
# def _rsi(series: pd.Series, length: int = 14) -> pd.Series:
#     delta = series.diff()
#     gain  = (delta.where(delta > 0, 0)).rolling(length).mean()
#     loss  = (-delta.where(delta < 0, 0)).rolling(length).mean()
#     rs    = gain / loss
#     return 100 - 100 / (1 + rs)
#
# def _atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
#     tr1 = (df['high'] - df['low']).abs()
#     tr2 = (df['high'] - df['close'].shift()).abs()
#     tr3 = (df['low']  - df['close'].shift()).abs()
#     tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
#     return tr.rolling(length).mean()
#
# def _adx(df: pd.DataFrame, length: int = 14) -> pd.Series:
#     """Very light ADX approximation (not Wilder-smoothed)."""
#     up   = df['high'].diff()
#     dn   = -df['low'].diff()
#     plus  = np.where((up > dn) & (up > 0), up, 0.0)
#     minus = np.where((dn > up) & (dn > 0), dn, 0.0)
#     atr   = _atr(df, length)
#     plus_di  = 100 * pd.Series(plus).rolling(length).sum() / atr
#     minus_di = 100 * pd.Series(minus).rolling(length).sum() / atr
#     dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
#     return dx.rolling(length).mean()
#
# # ------------------------------------------------------------------
# def calculate_target_price(price: float, pct: float) -> float:
#     return price * (1 + pct / 100)
#
# def strong_uptrend(df: pd.DataFrame) -> bool:
#     """Advanced 2 % breakout filter."""
#
#     close      = df['close']
#     high, low  = df['high'], df['low']
#     volume     = df['volume']
#     current    = close.iloc[-1]
#     recent_high = close.rolling(40).max().iloc[-2]   # use prev candle
#     ema20, ema50, ema200 = _ema(close, 20).iloc[-1], _ema(close, 50).iloc[-1], _ema(close, 200).iloc[-1]
#     rsi = _rsi(close).iloc[-1]
#     atr = _atr(df).iloc[-1]
#     adx = _adx(df).iloc[-1]
#
#     macd_fast = _ema(close, 12)
#     macd_slow = _ema(close, 26)
#     macd_hist = (macd_fast - macd_slow) - _ema(macd_fast - macd_slow, 9)
#     macd_rising = macd_hist.iloc[-1] > macd_hist.iloc[-2]
#
#     vol_spike = volume.iloc[-1] > 1.3 * volume.rolling(20).mean().iloc[-1]
#
#     breakout_ok = current > recent_high + 0.5 * atr      # ATR filter
#     ema_ok      = ema20 > ema50 > ema200
#     rsi_ok      = rsi > 55
#     adx_ok      = adx > 25
#     rr_ok       = calculate_target_price(current, TARGET_PERCENTAGE) - current <= atr  # TP ≤ 1ATR
#
#     # debug
#     print(f"close={current} recent_high={recent_high} ATR={atr}")
#     print(f"EMA test {ema_ok}, RSI={rsi:.1f}, ADX={adx:.1f}, MACD rising={macd_rising}, Vol spike={vol_spike}")
#
#     return all([breakout_ok, ema_ok, rsi_ok, adx_ok, macd_rising, vol_spike, rr_ok])
#
# # ------------------------------------------------------------------
# def predict_uptrend(pair: str) -> bool:
#     df = fetch_crypto_data(pair, timeframe='15m', limit=250)  # short-term bars
#     price = df['close'].iloc[-1]
#     tp    = calculate_target_price(price, TARGET_PERCENTAGE)
#
#     print(f"Current {pair}: {price:.6f}  |  2 % target: {tp:.6f}")
#
#     if strong_uptrend(df) and price < tp:
#         print(f"*** LONG setup on {pair} toward {tp:.6f}")
#         return True
#
#     print("No setup.")
#     return False

# strategies/uptrend_prediction.py
# ---------------------------------------------------------------
# import numpy as np
# import pandas as pd
# from utils.data_ingestion import fetch_crypto_data
# from config.configs import TARGET_PERCENTAGE          # e.g. 2.0
# from typing import Dict
#
# # ---------------- simple indicator helpers --------------------
# def _ema(series: pd.Series, span: int) -> pd.Series:
#     return series.ewm(span=span, adjust=False).mean()
#
# def _rsi(series: pd.Series, length: int = 14) -> pd.Series:
#     delta = series.diff()
#     gain  = delta.clip(lower=0).rolling(length).mean()
#     loss  = (-delta.clip(upper=0)).rolling(length).mean()
#     rs    = gain / loss
#     return 100 - 100 / (1 + rs)
#
# def _atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
#     tr = pd.concat([
#         (df["high"] - df["low"]).abs(),
#         (df["high"] - df["close"].shift()).abs(),
#         (df["low"]  - df["close"].shift()).abs()
#     ], axis=1).max(axis=1)
#     return tr.rolling(length).mean()
#
# def _adx(df: pd.DataFrame, length: int = 14) -> pd.Series:
#     up   = df["high"].diff()
#     dn   = -df["low"].diff()
#     plus  = np.where((up > dn) & (up > 0), up, 0.0)
#     minus = np.where((dn > up) & (dn > 0), dn, 0.0)
#     atr   = _atr(df, length)
#     plus_di  = 100 * pd.Series(plus).rolling(length).sum() / atr
#     minus_di = 100 * pd.Series(minus).rolling(length).sum() / atr
#     dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
#     return dx.rolling(length).mean()
#
# # -------------- weight table (sums to 100) --------------------
# WEIGHTS: Dict[str, int] = {
#     "breakout": 20,
#     "ema":      15,
#     "rsi":      15,
#     "adx":      15,
#     "macd":     15,
#     "volume":   10,
#     "rr":       10,
# }
#
# # ------------------- scoring function -------------------------
# def score_uptrend(df: pd.DataFrame) -> float:
#     close   = df["close"]
#     high    = df["high"];  volume = df["volume"]
#     cur     = close.iloc[-1]
#
#     recent_high = close.rolling(40).max().iloc[-2]      # prev candle
#     atr  = _atr(df).iloc[-1]
#
#     ema20, ema50, ema200 = (_ema(close, 20).iloc[-1],
#                              _ema(close, 50).iloc[-1],
#                              _ema(close,200).iloc[-1])
#
#     rsi = _rsi(close).iloc[-1]
#     adx = _adx(df).iloc[-1]
#
#     macd_fast = _ema(close,12)
#     macd_slow = _ema(close,26)
#     macd_hist = (macd_fast - macd_slow) - _ema(macd_fast - macd_slow, 9)
#     macd_rising = macd_hist.iloc[-1] > macd_hist.iloc[-2]
#
#     vol_spike = volume.iloc[-1] > 1.3 * volume.rolling(20).mean().iloc[-1]
#
#     tests = {
#         "breakout": cur > recent_high + 0.5 * atr,
#         "ema":      ema20 > ema50 > ema200,
#         "rsi":      rsi > 55,
#         "adx":      adx > 25,
#         "macd":     macd_rising,
#         "volume":   vol_spike,
#         "rr":       calculate_target_price(cur, TARGET_PERCENTAGE) - cur <= atr,
#     }
#
#     # Sum weights for passed tests
#     score = sum(WEIGHTS[k] for k, passed in tests.items() if passed)
#
#     # --- optional debug print ---------------------------------
#     debug = (f"SCORE BREAKDOWN  "
#              f"breakout={tests['breakout']}  ema={tests['ema']}  "
#              f"rsi={tests['rsi']}  adx={tests['adx']}  macd={tests['macd']}  "
#              f"vol={tests['volume']}  rr={tests['rr']}  --> {score}")
#     print(debug)
#
#     return score
#
# def calculate_target_price(price: float, pct: float) -> float:
#     return price * (1 + pct / 100)
#
# # ---------------- public API -----------------
# def predict_uptrend(pair: str) -> float:
#     """
#     Return a 0-100 score (higher = stronger short-term uptrend).
#     The calling code can decide its own cut-off (e.g. ≥70).
#     """
#     df    = fetch_crypto_data(pair, timeframe="15m", limit=250)
#     price = df["close"].iloc[-1]
#     score = score_uptrend(df)
#
#     print(f"{pair:10}  price={price:.6f}  score={score:.0f}/100")
#     return score

# strategies/uptrend_prediction.py
# ================================================================
"""
Return a numeric 0-100 score for short-term (≈2 %) breakout potential.
Scoring breakdown (default weights):

 breakout vs ATR          20
 EMA 20>50>200             15
 RSI > 55                  15
 ADX > 25                  15
 MACD histogram rising     15
 Volume spike 1.3×         10
 5-minute % change ≥0.30   10
 Risk/Reward ≤1 ATR        10
------------------------------------------------
 TOTAL                    100
"""
# import numpy as np
# import pandas as pd
# import ccxt
#
# from utils.data_ingestion import fetch_crypto_data
# from config.configs       import TARGET_PERCENTAGE
#
# BINANCE = ccxt.binance()
#
# # ---------------- indicator helpers ------------------------------
# def _ema(s: pd.Series, span: int) -> pd.Series:
#     return s.ewm(span=span, adjust=False).mean()
#
# def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
#     d = s.diff()
#     gain = d.clip(lower=0).rolling(n).mean()
#     loss = (-d.clip(upper=0)).rolling(n).mean()
#     rs = gain / loss
#     return 100 - 100 / (1 + rs)
#
# def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
#     tr = pd.concat([
#         (df['high'] - df['low']).abs(),
#         (df['high'] - df['close'].shift()).abs(),
#         (df['low']  - df['close'].shift()).abs()
#     ], axis=1).max(axis=1)
#     return tr.rolling(n).mean()
#
# def _adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
#     up = df['high'].diff()
#     dn = -df['low'].diff()
#     plus  = np.where((up > dn) & (up > 0), up, 0.0)
#     minus = np.where((dn > up) & (dn > 0), dn, 0.0)
#     atr = _atr(df, n)
#     plus_di  = 100 * pd.Series(plus).rolling(n).sum() / atr
#     minus_di = 100 * pd.Series(minus).rolling(n).sum() / atr
#     dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
#     return dx.rolling(n).mean()
#
# def _pct_change_5m(pair: str) -> float:
#     """Five 1-minute candles => 5-minute momentum."""
#     ohlcv = BINANCE.fetch_ohlcv(pair, timeframe='1m', limit=6)
#     closes = [c[4] for c in ohlcv]
#     return (closes[-1] - closes[0]) / closes[0] * 100
#
#
# # ---------------- scoring weights --------------------------------
# WEIGHTS = {
#     "breakout": 20,
#     "ema":      15,
#     "rsi":      15,
#     "adx":      15,
#     "macd":     15,
#     "volume":   10,
#     "pct5":     10,
#     "rr":       10,
# }
#
# # ---------------- target utility ---------------------------------
# def _target_price(p: float) -> float:
#     return p * (1 + TARGET_PERCENTAGE / 100)
#
# # ---------------- core score function ----------------------------
# def score_uptrend(df: pd.DataFrame, pair: str) -> int:
#     close  = df['close']; high = df['high']; vol = df['volume']
#     cur    = close.iloc[-1]
#
#     recent_high = close.rolling(40).max().iloc[-2]
#     atr  = _atr(df).iloc[-1]
#     ema20, ema50, ema200 = _ema(close,20).iloc[-1], _ema(close,50).iloc[-1], _ema(close,200).iloc[-1]
#     rsi  = _rsi(close).iloc[-1]
#     adx  = _adx(df).iloc[-1]
#
#     macd_fast = _ema(close,12)
#     macd_slow = _ema(close,26)
#     macd_hist = (macd_fast - macd_slow) - _ema(macd_fast - macd_slow, 9)
#     macd_up   = macd_hist.iloc[-1] > macd_hist.iloc[-2]
#
#     vol_spike = vol.iloc[-1] > 1.3 * vol.rolling(20).mean().iloc[-1]
#     pct5      = _pct_change_5m(pair)
#     rr_ok     = _target_price(cur) - cur <= atr
#
#     tests = {
#         "breakout": cur > recent_high + 0.5*atr,
#         "ema":      ema20 > ema50 > ema200,
#         "rsi":      rsi > 55,
#         "adx":      adx > 25,
#         "macd":     macd_up,
#         "volume":   vol_spike,
#         "pct5":     pct5 >= 0.30,
#         "rr":       rr_ok,
#     }
#
#     # --- score
#     score = sum(WEIGHTS[k] for k, ok in tests.items() if ok)
#
#     # --- debug
#     print(f"SCORE {pair}: {score}/100   pct5={pct5:.2f}%  "
#           f"{ {k:v for k,v in tests.items()} }")
#     return score
#
# # ---------------- external API -----------------------------------
# def predict_uptrend(pair: str) -> int:
#     df = fetch_crypto_data(pair, timeframe='15m', limit=250)
#     return score_uptrend(df, pair)


import numpy as np
import pandas as pd
import ccxt
from utils.data_ingestion import fetch_crypto_data
from config.configs import TARGET_PERCENTAGE

BINANCE = ccxt.binance()

# ---------------- Indicator Helpers -----------------------------
def _ema(s: pd.Series, span: int) -> pd.Series:
    """Exponential Moving Average (EMA)"""
    return s.ewm(span=span, adjust=False).mean()

def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    """Relative Strength Index (RSI)"""
    d = s.diff()
    gain = d.clip(lower=0).rolling(n).mean()
    loss = (-d.clip(upper=0)).rolling(n).mean()
    rs = gain / loss
    return 100 - 100 / (1 + rs)

def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Average True Range (ATR)"""
    tr = pd.concat([
        (df['high'] - df['low']).abs(),
        (df['high'] - df['close'].shift()).abs(),
        (df['low']  - df['close'].shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def _adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Average Directional Index (ADX)"""
    up = df['high'].diff()
    dn = -df['low'].diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr = _atr(df, n)
    plus_di = 100 * pd.Series(plus).rolling(n).sum() / atr
    minus_di = 100 * pd.Series(minus).rolling(n).sum() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return dx.rolling(n).mean()

def _pct_change_5m(pair: str) -> float:
    """Five 1-minute candles => 5-minute momentum"""
    ohlcv = BINANCE.fetch_ohlcv(pair, timeframe='1m', limit=6)
    closes = [c[4] for c in ohlcv]
    return (closes[-1] - closes[0]) / closes[0] * 100

# ---------------- Scoring Weights -------------------------------
WEIGHTS = {
    "breakout": 20,
    "ema":      15,
    "rsi":      15,
    "adx":      15,
    "macd":     15,
    "volume":   10,
    "pct5":     10,
    "rr":       10,
}

# ---------------- Target Price Calculation ----------------------
def _target_price(p: float) -> float:
    """Calculate target price based on percentage"""
    return p * (1 + TARGET_PERCENTAGE / 100)

# ---------------- Core Scoring Function -------------------------
def score_uptrend(df: pd.DataFrame, pair: str) -> int:
    """Calculate score for uptrend based on indicators and conditions"""
    close  = df['close']
    high   = df['high']
    vol    = df['volume']
    cur    = close.iloc[-1]

    # Calculate required indicators
    recent_high = close.rolling(40).max().iloc[-2]
    atr = _atr(df).iloc[-1]
    ema20, ema50, ema200 = _ema(close, 20).iloc[-1], _ema(close, 50).iloc[-1], _ema(close, 200).iloc[-1]
    rsi = _rsi(close).iloc[-1]
    adx = _adx(df).iloc[-1]

    macd_fast = _ema(close, 12)
    macd_slow = _ema(close, 26)
    macd_hist = (macd_fast - macd_slow) - _ema(macd_fast - macd_slow, 9)
    macd_up = macd_hist.iloc[-1] > macd_hist.iloc[-2]

    vol_spike = vol.iloc[-1] > 1.3 * vol.rolling(20).mean().iloc[-1]
    pct5 = _pct_change_5m(pair)
    rr_ok = _target_price(cur) - cur <= atr

    # Define scoring conditions
    tests = {
        "breakout": cur > recent_high + 0.5 * atr,
        "ema": ema20 > ema50 > ema200,
        "rsi": rsi > 55,
        "adx": adx > 25,
        "macd": macd_up,
        "volume": vol_spike,
        "pct5": pct5 >= 0.30,
        "rr": rr_ok,
    }

    # Calculate the final score
    score = sum(WEIGHTS[k] for k, ok in tests.items() if ok)

    # Debugging output for understanding the conditions
    print(f"SCORE {pair}: {score}/100   pct5={pct5:.2f}%  "
          f"{ {k:v for k,v in tests.items()} }")
    return score

# ---------------- External API Function ------------------------
def predict_uptrend(pair: str) -> int:
    """Fetch data and predict uptrend for the pair"""
    try:
        df = fetch_crypto_data(pair, timeframe='15m', limit=250)
        return score_uptrend(df, pair)
    except Exception as e:
        print(f"Error fetching data or calculating score for {pair}: {e}")
        return 0

# ---------------- Example of Usage -----------------------------
if __name__ == "__main__":
    # Example pair: 'BTC/USDT'
    pair = 'BTC/USDT'
    score = predict_uptrend(pair)
    print(f"Final score for {pair}: {score}")
