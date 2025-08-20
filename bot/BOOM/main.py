"""
Trading-bot driver
==================
Phase A  : score every pair, open those ≥ THRESHOLD_SCORE
Phase B  : babysit open positions until all flat
Loop     : refresh the tradable-pair universe, repeat
"""

import time
from strategies.uptrend_prediction import predict_uptrend
from utils.data_ingestion  import get_selected_crypto_data
from utils.execution       import FakeExecution
from utils.risk_management import RiskManager
from config.configs        import FAKE_MONEY, RISK_CONFIG
from utils.update_pairs    import main as refresh_pairs

# ------------------------------ settings --------------------------
THRESHOLD_SCORE = 60        # ignore weaker setups
MAX_PER_SCAN    = None      # or an int → cap # entries per scan
COOLDOWN_SEC    = 3600      # don’t re-enter same coin for 1 h

# ------------------------------ helpers --------------------------
def last_prices() -> dict[str, float]:
    """Fetch latest close price for every selected pair."""
    data = get_selected_crypto_data()
    return {p: df["close"].iloc[-1] for p, df in data.items()}


# -----------------------------------------------------------------
def scan_for_opportunities(exe: FakeExecution,
                           risk: RiskManager) -> None:
    """
    Score every pair; open trades (best-score first) until either
    target cut-off or risk cap reached.
    """
    prices = last_prices()
    scored: list[tuple[int, str]] = []

    for pair in RISK_CONFIG["SELECTED_CRYPTO_PAIRS"]:
        exe.print_filters_for_pair(pair)
        if exe.recently_traded(pair, COOLDOWN_SEC):
            print(f"Skip {pair}: traded within last hour.")
            continue

        print(f"\n--- Scoring {pair} ---")
        score = predict_uptrend(pair)                  # 0-100
        scored.append((score, pair))

    scored.sort(reverse=True)                          # high → low

    opened = 0
    for score, pair in scored:
        if score < THRESHOLD_SCORE:
            break

        if risk.max_concurrent_reached(exe):
            print("Risk cap reached; no more entries this scan.")
            break

        if MAX_PER_SCAN and opened >= MAX_PER_SCAN:
            break

        stake = risk.calculate_position_size("buy")
        if stake <= 0:
            print("No free capital; skipping.")
            continue

        print(f"OPEN  {pair:<12}  score={score:>3}  stake={stake:.2f} USDT")
        exe.execute_trade("buy", pair, stake, prices[pair])
        opened += 1

    if opened == 0:
        print("No opportunities met the threshold.")


# -----------------------------------------------------------------
def monitor_open_positions(exe: FakeExecution,
                           poll_sec: float = 0.5) -> None:
    """Block until *all* open positions are closed."""
    while exe.has_open_positions():
        exe.track_positions(last_prices())
        time.sleep(poll_sec)


# -----------------------------------------------------------------
def run_trading_bot():
    risk_params = {k: RISK_CONFIG[k] for k in (
        "max_percent_per_trade",
        "daily_drawdown_limit_percent",
        "max_concurrent_trades")}

    exe  = FakeExecution(FAKE_MONEY)

    risk = RiskManager(balance=FAKE_MONEY, **risk_params)

    while True:
        # -------- Phase A: new entries ------------------------------
        scan_for_opportunities(exe, risk)

        # -------- Phase B: babysit them until flat ------------------
        if exe.has_open_positions():
            monitor_open_positions(exe)
        else:
            print("No trades opened on this scan.")

        # -------- refresh tradable universe & repeat ---------------
        refresh_pairs()               # updates .env with new gainers
        print("\n-- universe refreshed; rescanning --\n")
        time.sleep(2)                 # tiny pause to avoid tight loop


# -----------------------------------------------------------------
if __name__ == "__main__":
    refresh_pairs()  # updates .env with new gainers
    run_trading_bot()
