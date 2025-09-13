# telegram_trader_bot.py
# Dependencies:
#   python-telegram-bot>=22,<23
#   ccxt, numpy, pandas, scipy, matplotlib

import os, sys, asyncio, pathlib, json, time, io
from typing import Final, Optional, List, Dict, Any, Sequence, Tuple
from dataclasses import dataclass
from datetime import datetime

# --- Headless matplotlib for servers ---
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import numpy as np
import pandas as pd
import ccxt
from scipy.signal import savgol_filter, find_peaks

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler,
    CallbackQueryHandler, filters
)

# ========= CONFIG =========
TOKEN = "---"  # ← your BotFather token
BOT_USERNAME: Final = "@TB00M_BOT"

# Folder where your trading script runs
TRADER_CWD = pathlib.Path(r"C:\Users\rania\OneDrive\Bureau\SCRAP\bot\BOOM")
TRADER_SCRIPT = TRADER_CWD / "main.py"
TRADER_ARGS: List[str] = []

# Log file produced by your trading bot (used to list open positions)
LOG_JSON_PATH = TRADER_CWD / "trade_log.json"

# Runtime log for subprocess stdout/stderr
RUNTIME_LOG_PATH = TRADER_CWD / "trader_stdout.log"

# ========= UI (Main Keyboard) =========
def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🟢 Start Bot", callback_data="BUY_START"),
        InlineKeyboardButton("🔴 Stop Bot", callback_data="SELL_STOP"),
        InlineKeyboardButton("📈 Open Positions", callback_data="POSITIONS_SHOW"),
        InlineKeyboardButton("📊 Raw Log (log.json)", callback_data="POSITIONS_FILE"),
    ]])

# ========= Start/Stop subprocess (your trading script) =========
def _proc_running(app: Application) -> bool:
    proc: Optional[asyncio.subprocess.Process] = app.bot_data.get("trader_proc")
    return (proc is not None) and (proc.returncode is None)

async def _start_trader(app: Application) -> str:
    if _proc_running(app):
        return "ℹ️ Trading bot is already running."
    if not TRADER_SCRIPT.exists():
        return f"❌ Script not found: {TRADER_SCRIPT}"

    logf = open(RUNTIME_LOG_PATH, "ab", buffering=0)
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(TRADER_SCRIPT), *TRADER_ARGS,
            cwd=str(TRADER_CWD),
            stdout=logf,
            stderr=logf,
        )
        app.bot_data["trader_proc"] = proc
        app.bot_data["trader_logf"] = logf
        return f"✅ Trading bot started (PID={proc.pid})."
    except Exception as e:
        logf.close()
        return f"❌ Failed to start: {e}"

async def _stop_trader(app: Application) -> str:
    proc: Optional[asyncio.subprocess.Process] = app.bot_data.get("trader_proc")
    logf = app.bot_data.get("trader_logf")

    if not proc or proc.returncode is not None:
        if logf:
            try: logf.close()
            except: pass
        app.bot_data.pop("trader_proc", None)
        app.bot_data.pop("trader_logf", None)
        return "ℹ️ No trading bot running."

    try:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=8)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        code = proc.returncode
        return f"🛑 Trading bot stopped (code={code})."
    finally:
        if logf:
            try: logf.close()
            except: pass
        app.bot_data.pop("trader_proc", None)
        app.bot_data.pop("trader_logf", None)

# ========= Positions snapshot from log.json =========
def _load_open_positions_from_log(log_path: pathlib.Path) -> List[Dict[str, Any]]:
    if not log_path.exists() or not log_path.is_file():
        return []

    def _key_for(rec):
        for k in ("position_id", "id", "order_id", "pid"):
            if k in rec:
                return ("id", str(rec[k]))
        sym = str(rec.get("symbol") or rec.get("pair") or rec.get("market") or "?").upper()
        side = str(rec.get("side") or rec.get("direction") or "?").upper()
        return ("sym", f"{sym}:{side}")

    def _is_open_status(s):
        if not s: return None
        s = str(s).upper()
        if s in ("OPEN", "OPENED", "RUNNING", "ACTIVE"): return True
        if s in ("CLOSE", "CLOSED", "EXITED", "INACTIVE"): return False
        return None

    try:
        raw = log_path.read_text(encoding="utf-8", errors="ignore").strip()
        if not raw: return []
        if raw[0] == "[":
            records = json.loads(raw)
            if not isinstance(records, list): records = [records]
        else:
            records = []
            for line in raw.splitlines():
                line = line.strip()
                if not line: continue
                try: records.append(json.loads(line))
                except: pass
    except Exception:
        return []

    positions: Dict[Any, Dict[str, Any]] = {}
    for rec in records:
        if not isinstance(rec, dict): continue
        key = _key_for(rec)
        p = positions.get(key, {
            "id": None, "symbol": None, "side": None,
            "qty": None, "entry_price": None, "entry_time": None,
            "status": "OPEN", "updates": 0,
        })
        p["id"] = p["id"] or (rec.get("position_id") or rec.get("id") or rec.get("order_id") or rec.get("pid"))
        p["symbol"] = (rec.get("symbol") or rec.get("pair") or p["symbol"])
        p["side"] = (rec.get("side") or rec.get("direction") or p["side"])
        p["qty"] = (rec.get("qty") or rec.get("quantity") or rec.get("size") or p["qty"])
        p["entry_price"] = (rec.get("entry_price") or rec.get("price") or p["entry_price"])

        ts = rec.get("time") or rec.get("timestamp") or rec.get("ts")
        if ts and not p["entry_time"]:
            try:
                if isinstance(ts, (int, float)):
                    p["entry_time"] = datetime.fromtimestamp(
                        float(ts)/1000 if float(ts) > 1e12 else float(ts)
                    ).isoformat(timespec="seconds")
                elif isinstance(ts, str):
                    p["entry_time"] = ts
            except: pass

        sflag = _is_open_status(rec.get("status"))
        if sflag is True: p["status"] = "OPEN"
        elif sflag is False: p["status"] = "CLOSED"

        ev = str(rec.get("event") or rec.get("type") or "").lower()
        if ev in ("open", "opened", "entry"): p["status"] = "OPEN"
        elif ev in ("close", "closed", "exit"): p["status"] = "CLOSED"

        p["updates"] += 1
        positions[key] = p

    opened = [v for v in positions.values() if v.get("status") == "OPEN"]
    opened.sort(key=lambda x: (str(x.get("symbol") or ""), str(x.get("side") or "")))
    return opened

def _format_positions_list(opened: List[Dict[str, Any]]) -> str:
    if not opened:
        return "✅ *No open positions at the moment.*"
    lines = ["📈 *Open Positions*:"]
    for p in opened:
        sym = (p.get("symbol") or "?").upper()
        side = (p.get("side") or "?").upper()
        qty = p.get("qty") or "?"
        price = p.get("entry_price") or "?"
        t0 = p.get("entry_time") or "—"
        pid = p.get("id")
        header = f"• *{sym} {side}*"
        if pid: header += f" (id: `{pid}`)"
        lines.append(header)
        lines.append(f"   Qty: {qty} | Entry: {price} | Since: {t0}")
    return "\n".join(lines)

# ========= Chart utilities (integrated from your analysis script) =========
EXCHANGE = ccxt.binance()

def _normalize_symbol(sym: str) -> str:
    s = sym.strip().upper()
    if "/" in s: return s
    if s.endswith("USDT"): return f"{s[:-4]}/USDT"
    return s

def fetch_ccxt_ohlcv(symbol: str, timeframe: str = "5m", limit: int = 900) -> pd.DataFrame:
    sym = _normalize_symbol(symbol)
    ohlcv = EXCHANGE.fetch_ohlcv(sym, timeframe=timeframe, limit=limit)  # [ms,o,h,l,c,v]
    df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df.set_index("ts", inplace=True)
    return df

def resample_to(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """
    Resample OHLCV to a pandas rule (e.g., '10T' for 10 minutes).
    """
    o = df["open"].resample(rule).first()
    h = df["high"].resample(rule).max()
    l = df["low"].resample(rule).min()
    c = df["close"].resample(rule).last()
    v = df["volume"].resample(rule).sum()
    out = pd.concat([o, h, l, c, v], axis=1)
    out.columns = ["open", "high", "low", "close", "volume"]
    out = out.dropna()
    return out

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr = pd.concat([
        (df["high"] - df["low"]).abs(),
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def smooth_close(close: pd.Series, window_length: int = 49, polyorder: int = 5) -> pd.Series:
    n = len(close)
    if n < 5:
        return close.rename("close_smooth")
    wl = min(window_length, n if n % 2 == 1 else n - 1)
    wl = max(5, wl)
    wl = wl if wl % 2 == 1 else wl - 1
    return pd.Series(savgol_filter(close.values, wl, polyorder),
                     index=close.index, name="close_smooth")

@dataclass
class Extrema:
    peaks_idx: np.ndarray
    troughs_idx: np.ndarray

def find_extrema_from_smooth(close_smooth: pd.Series,
                             base_prom: float,
                             distance: int = 15,
                             width: int = 3) -> Extrema:
    prom = max(float(base_prom), 1e-12)
    peaks_idx, _ = find_peaks(close_smooth.values, distance=distance, width=width, prominence=prom)
    troughs_idx, _ = find_peaks(-close_smooth.values, distance=distance, width=width, prominence=prom)
    return Extrema(peaks_idx=peaks_idx, troughs_idx=troughs_idx)

@dataclass
class TrendSpan:
    start_i: int
    end_i: int
    label: str  # "UP" or "DOWN"

def _last_two(ix: Sequence[int]) -> Tuple[int, int] | None:
    if len(ix) < 2: return None
    return ix[-2], ix[-1]

def _trend_rule(close_s: pd.Series, peaks_hist: List[int], troughs_hist: List[int]) -> str | None:
    pp = _last_two(peaks_hist)
    tt = _last_two(troughs_hist)
    if pp is None or tt is None: return None
    p1, p2 = pp; t1, t2 = tt
    if close_s.iloc[p2] > close_s.iloc[p1] and close_s.iloc[t2] > close_s.iloc[t1]:
        return "UP"
    if close_s.iloc[p2] < close_s.iloc[p1] and close_s.iloc[t2] < close_s.iloc[t1]:
        return "DOWN"
    return None

def _merge_spans(spans: List[TrendSpan]) -> List[TrendSpan]:
    if not spans: return spans
    spans.sort(key=lambda s: (s.start_i, s.end_i))
    out = [spans[0]]
    for s in spans[1:]:
        last = out[-1]
        if s.label == last.label and s.start_i <= last.end_i + 1:
            last.end_i = max(last.end_i, s.end_i)
        else:
            out.append(s)
    return out

def detect_trend_spans_from_dots(close_s: pd.Series,
                                 peaks_idx: np.ndarray,
                                 troughs_idx: np.ndarray) -> List[TrendSpan]:
    tagged = [(int(i), "peak") for i in peaks_idx] + [(int(i), "trough") for i in troughs_idx]
    tagged.sort(key=lambda x: x[0])

    spans: List[TrendSpan] = []
    cur: str | None = None
    span_start: int | None = None
    peaks_seen: List[int] = []
    troughs_seen: List[int] = []

    for pos, kind in tagged:
        if kind == "peak": peaks_seen.append(pos)
        else: troughs_seen.append(pos)

        now = _trend_rule(close_s, peaks_seen, troughs_seen)

        if now is not None and cur is None:
            cur = now
            p2 = _last_two(peaks_seen)
            t2 = _last_two(troughs_seen)
            anchor = max(p2[0], t2[0]) if p2 and t2 else pos
            span_start = anchor

        elif now is not None and cur is not None and now != cur:
            spans.append(TrendSpan(start_i=span_start, end_i=pos, label=cur))
            cur = now
            p2 = _last_two(peaks_seen)
            t2 = _last_two(troughs_seen)
            anchor = max(p2[0], t2[0]) if p2 and t2 else pos
            span_start = anchor

    if cur is not None and span_start is not None:
        spans.append(TrendSpan(start_i=span_start, end_i=len(close_s) - 1, label=cur))

    return _merge_spans(spans)

def plot_snapshot_with_trend_zones(df: pd.DataFrame, first_n: int = 500,
                                   distance: int = 15, width: int = 3) -> Tuple[plt.Figure, plt.Axes]:
    if len(df) == 0:
        raise ValueError("Empty DataFrame; nothing to plot.")
    df2 = df.iloc[:first_n].copy()
    df2["close_smooth"] = smooth_close(df2["close"])
    df2["atr_raw"] = atr(df2)
    df2["atr"] = df2["atr_raw"].rolling(30, min_periods=1).mean()
    base_prom = float(df2["atr"].iloc[-1] or df2["atr"].dropna().median() or 0.0)

    ex = find_extrema_from_smooth(df2["close_smooth"], base_prom=base_prom,
                                  distance=distance, width=width)
    spans = detect_trend_spans_from_dots(df2["close_smooth"], ex.peaks_idx, ex.troughs_idx)

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(df2.index, df2["close"], lw=2, alpha=0.35, color="grey", label="close")
    ax.plot(df2.index, df2["close_smooth"], lw=2.5, color="orange", label="smoothed")

    ax.scatter(df2.index[ex.peaks_idx], df2["close_smooth"].iloc[ex.peaks_idx],
               s=44, color="red", label="peaks", zorder=5)
    ax.scatter(df2.index[ex.troughs_idx], df2["close_smooth"].iloc[ex.troughs_idx],
               s=44, color="green", label="troughs", zorder=5)

    for s in spans:
        x0 = df2.index[int(s.start_i)]
        x1 = df2.index[int(s.end_i)]
        if s.label == "UP":
            ax.axvspan(x0, x1, color=(0.60, 1.00, 0.62, 0.20))
        else:
            ax.axvspan(x0, x1, color=(1.00, 0.60, 0.60, 0.16))
        y0 = df2["close_smooth"].iloc[s.start_i]
        ax.text(x0, y0, s.label, color=("green" if s.label == "UP" else "crimson"),
                fontsize=9, fontweight="bold", va="bottom", ha="left")

    ax.set_title("Price vs Smoothed Close — Trend zones from extrema rule")
    ax.legend(loc="upper left")
    plt.xticks(rotation=30)
    plt.tight_layout()
    return fig, ax

def make_chart_png(symbol: str, timeframe: str, limit: int = 600, first_n: int = 500) -> bytes:
    """
    Builds the chart and returns a PNG bytes buffer.
    - timeframe supports '5m', '15m', and '10m' (via 5m fetch + resample to 10m).
    """
    tf = timeframe.lower()
    if tf not in {"5m", "10m", "15m"}:
        raise ValueError("Unsupported timeframe. Use 5m, 10m, or 15m.")

    if tf == "10m":
        # fetch more 5m data then resample to 10 minutes
        base_tf = "5m"
        df5 = fetch_ccxt_ohlcv(symbol, timeframe=base_tf, limit=max(limit, first_n) * 2)
        df = resample_to(df5, "10T")
    else:
        df = fetch_ccxt_ohlcv(symbol, timeframe=tf, limit=max(limit, first_n))

    fig, _ = plot_snapshot_with_trend_zones(df, first_n=min(first_n, len(df)))
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()

# ========= Hooks for Buy/Sell/Empty (placeholder) =========
async def on_user_buy(position: Dict[str, Any]) -> str:
    sym = (position.get("symbol") or "?").upper()
    side = (position.get("side") or "?").upper()
    return f"✅ BUY executed for {sym} {side}"

async def on_user_sell(position: Dict[str, Any]) -> str:
    sym = (position.get("symbol") or "?").upper()
    side = (position.get("side") or "?").upper()
    return f"✅ SELL executed for {sym} {side}"

async def on_user_empty(position: Dict[str, Any]) -> str:
    sym = (position.get("symbol") or "?").upper()
    side = (position.get("side") or "?").upper()
    return f"🟨 EMPTY (no action) for {sym} {side}"

# ========= Commands =========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! I'm your trading bot.\nChoose an action:", reply_markup=main_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🟢 Start Bot = launch trading script\n"
        "🔴 Stop Bot = stop trading script\n"
        "📈 Open Positions = show list + actions + chart\n"
        "📊 Raw Log = send raw log.json"
    )

def handle_response(text: str) -> str:
    t = (text or "").lower()
    if "hello" in t: return "Hello! How can I assist you today?"
    if "how are you" in t: return "I'm just a bot, but thanks for asking!"
    if "name" in t: return "I'm a Telegram trading bot."
    return "I'm sorry, I didn't understand that."

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = handle_response(update.message.text)
    await update.message.reply_text(response, reply_markup=main_keyboard())

# ========= Inline keyboards for Positions flow =========
def _generic_positions_keyboard() -> InlineKeyboardMarkup:
    """
    After showing positions, present action buttons including Chart.
    """
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🟢 Buy", callback_data="POSSEL|BUY"),
        InlineKeyboardButton("🔴 Sell", callback_data="POSSEL|SELL"),
        InlineKeyboardButton("🟨 Empty", callback_data="POSSEL|EMPTY"),
    ],[
        InlineKeyboardButton("📉 Chart", callback_data="POSCHART"),
        InlineKeyboardButton("↩️ Cancel", callback_data="CANCEL"),
    ]])

def _choose_timeframe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("5m", callback_data="CHTF|5m"),
        InlineKeyboardButton("10m", callback_data="CHTF|10m"),
        InlineKeyboardButton("15m", callback_data="CHTF|15m"),
    ],[
        InlineKeyboardButton("↩️ Cancel", callback_data="CANCEL"),
    ]])

def _choose_symbol_keyboard(opened: List[Dict[str, Any]], action_tag: str) -> InlineKeyboardMarkup:
    """
    action_tag is either 'DOACT' (for Buy/Sell/Empty) or 'DOCHART' (for charts).
    Buttons carry index into snapshot or default symbols.
    """
    buttons: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for i, p in enumerate(opened):
        sym = (p.get("symbol") or f"#{i+1}").upper()
        side = (p.get("side") or "?").upper()
        label = f"{sym} {side}"
        row.append(InlineKeyboardButton(label, callback_data=f"{action_tag}|IDX|{i}"))
        if len(row) == 3:
            buttons.append(row); row = []
    if row: buttons.append(row)

    # If no open positions, offer defaults
    if not opened:
        defaults = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
        row = []
        for sym in defaults:
            row.append(InlineKeyboardButton(sym, callback_data=f"{action_tag}|SYM|{sym}"))
            if len(row) == 3:
                buttons.append(row); row = []
        if row: buttons.append(row)

    buttons.append([InlineKeyboardButton("↩️ Cancel", callback_data="CANCEL")])
    return InlineKeyboardMarkup(buttons)

# ========= Callback handling =========
async def on_action_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data

    # Start/Stop bot
    if action == "BUY_START":
        msg = await _start_trader(context.application)
        await query.message.reply_text(msg, reply_markup=main_keyboard()); return
    if action == "SELL_STOP":
        msg = await _stop_trader(context.application)
        await query.message.reply_text(msg, reply_markup=main_keyboard()); return

    # Show positions + actions + Chart
    if action == "POSITIONS_SHOW":
        opened = _load_open_positions_from_log(LOG_JSON_PATH)
        context.application.bot_data["last_positions_snapshot"] = opened
        context.application.bot_data["last_positions_time"] = time.time()

        text = _format_positions_list(opened)
        await query.message.reply_text(
            text, parse_mode=ParseMode.MARKDOWN, reply_markup=_generic_positions_keyboard()
        )
        return

    # Generic actions (Buy/Sell/Empty) — Step 1: choose action
    if action.startswith("POSSEL|"):
        _, act = action.split("|", 1)
        opened = context.application.bot_data.get("last_positions_snapshot") or []
        if not opened:
            await query.message.reply_text("ℹ️ No open positions right now.", reply_markup=main_keyboard()); return
        context.application.bot_data["last_action"] = act  # remember chosen action
        await query.message.reply_text(
            f"Select the symbol to *{act}*:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_choose_symbol_keyboard(opened, "DOACT")
        )
        return

    # Generic actions (Buy/Sell/Empty) — Step 2: choose symbol
    if action.startswith("DOACT|"):
        # formats: DOACT|IDX|<i> or DOACT|SYM|<symbol>
        parts = action.split("|", 3)
        if len(parts) < 3:
            await query.message.reply_text("❌ Invalid action.", reply_markup=main_keyboard()); return
        mode = parts[1]
        act = context.application.bot_data.get("last_action") or "EMPTY"

        opened = context.application.bot_data.get("last_positions_snapshot") or []
        if mode == "IDX":
            try: idx = int(parts[2])
            except: idx = -1
            if not opened or idx < 0 or idx >= len(opened):
                await query.message.reply_text("⚠️ No positions available. Press *Open Positions* again.",
                                               parse_mode=ParseMode.MARKDOWN, reply_markup=main_keyboard()); return
            pos = opened[idx]
        else:  # SYM chosen (not used for DOACT in current flow)
            sym = parts[2]
            pos = {"symbol": sym, "side": "?"}

        if act == "BUY": user_msg = await on_user_buy(pos)
        elif act == "SELL": user_msg = await on_user_sell(pos)
        else: user_msg = await on_user_empty(pos)

        await query.message.reply_text(user_msg, reply_markup=main_keyboard()); return

    # Chart flow — Step 1: choose timeframe (always available under Positions)
    if action == "POSCHART":
        await query.message.reply_text(
            "Choose timeframe for the chart:",
            reply_markup=_choose_timeframe_keyboard()
        )
        return

    # Chart flow — Step 2: timeframe picked → choose symbol
    if action.startswith("CHTF|"):
        _, tf = action.split("|", 1)
        context.application.bot_data["chart_tf"] = tf
        opened = context.application.bot_data.get("last_positions_snapshot") or []
        await query.message.reply_text(
            f"Choose the symbol to chart ({tf}):",
            reply_markup=_choose_symbol_keyboard(opened, "DOCHART")
        )
        return

    # Chart flow — Step 3: symbol picked → generate and send image
    if action.startswith("DOCHART|"):
        parts = action.split("|", 3)
        if len(parts) < 3:
            await query.message.reply_text("❌ Invalid chart request.", reply_markup=main_keyboard()); return
        mode = parts[1]
        tf = context.application.bot_data.get("chart_tf", "5m")
        opened = context.application.bot_data.get("last_positions_snapshot") or []

        if mode == "IDX":
            try: idx = int(parts[2])
            except: idx = -1
            if not opened or idx < 0 or idx >= len(opened):
                await query.message.reply_text("⚠️ No positions available to pick from.",
                                               reply_markup=main_keyboard()); return
            sym = (opened[idx].get("symbol") or "BTC/USDT")
        else:  # SYM|<symbol>
            sym = parts[2]

        try:
            await query.message.reply_text(f"Rendering chart for *{sym}* ({tf}) …", parse_mode=ParseMode.MARKDOWN)
            png = make_chart_png(sym, tf, limit=700, first_n=600)
            await query.message.reply_photo(photo=png, caption=f"{sym} — timeframe {tf}")
        except Exception as e:
            await query.message.reply_text(f"❌ Could not render chart: {e}")
        return

    # Cancel
    if action == "CANCEL":
        await query.message.reply_text("Cancelled. What do you want to do next?", reply_markup=main_keyboard())
        return

    # Send raw log
    if action == "POSITIONS_FILE":
        if LOG_JSON_PATH.exists() and LOG_JSON_PATH.is_file():
            try:
                with open(LOG_JSON_PATH, "rb") as f:
                    await query.message.reply_document(
                        document=f, filename=LOG_JSON_PATH.name, caption="Here is your log.json"
                    )
            except Exception as e:
                await query.message.reply_text(f"❌ Could not send log.json: {e}")
        else:
            await query.message.reply_text(f"❗ File not found: {LOG_JSON_PATH}")
        return

# ========= Errors =========
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print(f"[ERROR] {context.error}")

# ========= Main =========
async def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(
        on_action_click,
        pattern=r"^(BUY_START|SELL_STOP|POSITIONS_SHOW|POSITIONS_FILE|POSSEL\|.*|DOACT\|.*|POSCHART|CHTF\|.*|DOCHART\|.*|CANCEL)$"
    ))
    app.add_error_handler(error_handler)

    await app.initialize()
    await app.start()
    print("Polling… (Ctrl+C to stop)")
    await app.updater.start_polling()

    try:
        await asyncio.Future()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        if _proc_running(app):
            await _stop_trader(app)
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
