# utils/auto_levels.py
# ======================================================================
# Automatic resistance detection & channel fitting (NumPy/Pandas only).
# API:
#   - resistance_context(df5, cur_price=None, atr_value=None, ...)
#       -> dict with horizontal levels, channel lines, distances, veto flag
#   - near_resistance_veto(df5, cur_price=None, atr_value=None, ...)
#       -> (bool, ctx)  # True = avoid/skip
# ======================================================================

from __future__ import annotations
import numpy as np
import pandas as pd

# ------------------------------ ATR -----------------------------------

def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift()
    tr = pd.concat([
        (high - low).abs(),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()

# ------------------------------ swings ---------------------------------

def _swing_high_mask(s: pd.Series, left: int = 3, right: int = 3) -> pd.Series:
    """
    True where s[i] is a swing high vs neighbors (window size = left+right+1).
    """
    w = left + right + 1
    mask = s.shift(-right).rolling(w).apply(
        lambda arr: float(arr[right] == np.max(arr) and arr[right] > arr[right-1] and arr[right] > arr[right+1]),
        raw=True
    )
    return (mask == 1.0).fillna(False)

def _cluster_levels(levels: np.ndarray, tol: float) -> list[float]:
    """
    Greedy cluster of price levels within ±tol; return cluster means sorted
    by cluster size (touches) then level value (desc).
    """
    if len(levels) == 0:
        return []
    lv = np.sort(levels)
    clusters = []
    cur = [lv[0]]
    for x in lv[1:]:
        if abs(x - np.mean(cur)) <= tol:
            cur.append(x)
        else:
            clusters.append(cur)
            cur = [x]
    clusters.append(cur)
    clusters.sort(key=lambda c: (len(c), np.mean(c)), reverse=True)
    return [float(np.mean(c)) for c in clusters]

# ------------------------------ detectors ------------------------------

def detect_horizontal_resistances(
    df5: pd.DataFrame,
    lookback: int = 240,             # ~20h of 5m bars
    left: int = 3,
    right: int = 3,
    atr_buffer_frac: float = 0.30,   # tolerance uses max(0.10%, 0.30×ATR)
    top_k: int = 5,
) -> list[float]:
    """
    Strong horizontal resistances from clustered swing highs.
    Only returns levels >= current close (things we can run into).
    """
    sub = df5.tail(lookback).copy()
    cur = float(sub["close"].iloc[-1])
    atr = float(_atr(sub).iloc[-1])
    tol = max(0.0010 * cur, atr_buffer_frac * atr)  # 0.10% or 0.30×ATR

    mask = _swing_high_mask(sub["high"], left=left, right=right)
    swings = sub.loc[mask, "high"].values
    clustered = _cluster_levels(swings, tol)
    levels = [lv for lv in clustered if lv >= cur]
    return levels[:top_k]

def fit_up_channel(
    df5: pd.DataFrame,
    lookback: int = 180,     # last 15h
    upper_q: float = 0.95,
    lower_q: float = 0.05,
) -> tuple[float, float, float]:
    """
    Linear-regression channel on closes; returns (upper_now, lower_now, slope).
    """
    sub = df5.tail(lookback).copy()
    y = sub["close"].to_numpy(dtype=float)
    t = np.arange(len(y), dtype=float)
    m, b = np.polyfit(t, y, 1)          # baseline
    base = m * t + b
    resid = y - base
    upper_off = float(np.quantile(resid, upper_q))
    lower_off = float(np.quantile(resid, lower_q))
    t_now = float(len(y) - 1)
    base_now = m * t_now + b
    upper_now = base_now + upper_off
    lower_now = base_now + lower_off
    return float(upper_now), float(lower_now), float(m)

# ------------------------------ buffers & API --------------------------

def resistance_buffer(cur: float, atr: float) -> float:
    """
    Safety margin before resistance, large enough to still allow +0.20% TP.
    """
    return max(0.0012 * cur, 0.40 * atr)  # 0.12% of price or 0.4×ATR

def resistance_context(
    df5: pd.DataFrame,
    cur_price: float | None = None,
    atr_value: float | None = None,
    *,
    lookback_levels: int = 240,
    lookback_channel: int = 180,
) -> dict:
    """
    Compute auto-detected resistances + distances and a veto flag.
    """
    cur = float(df5["close"].iloc[-1]) if cur_price is None else float(cur_price)
    atr = float(_atr(df5).iloc[-1])     if atr_value is None else float(atr_value)

    h_levels = detect_horizontal_resistances(df5, lookback=lookback_levels)
    upper_now, lower_now, slope = fit_up_channel(df5, lookback=lookback_channel)
    buf = resistance_buffer(cur, atr)

    d_horiz = min((abs(cur - lv) for lv in h_levels), default=np.inf)
    d_chan  = abs(cur - upper_now)
    near = (d_horiz <= buf) or (d_chan <= buf)

    return {
        "cur": cur, "atr": atr, "buffer": buf,
        "h_levels": h_levels, "upper_now": upper_now, "lower_now": lower_now, "slope": slope,
        "d_horiz": d_horiz, "d_chan": d_chan, "near_resistance": near,
    }

def near_resistance_veto(
    df5: pd.DataFrame,
    cur_price: float | None = None,
    atr_value: float | None = None,
    **ctx_kwargs
) -> tuple[bool, dict]:
    """
    Convenience: returns (should_skip, ctx). True means: avoid trade.
    """
    ctx = resistance_context(df5, cur_price, atr_value, **ctx_kwargs)
    return bool(ctx["near_resistance"]), ctx
