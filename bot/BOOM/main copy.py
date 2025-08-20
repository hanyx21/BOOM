# from strategies.uptrend_prediction import predict_uptrend
# from utils.execution import FakeExecution
# from utils.risk_management import RiskManager
# from config.configs import FAKE_MONEY, RISK_CONFIG
#
#
# def run_trading_bot():
#     # Extract relevant parameters from RISK_CONFIG
#     max_percent_per_trade = RISK_CONFIG['max_percent_per_trade']
#     daily_drawdown_limit_percent = RISK_CONFIG['daily_drawdown_limit_percent']
#     max_concurrent_trades = RISK_CONFIG['max_concurrent_trades']
#
#     # Initialize Fake Execution and Risk Management with extracted parameters
#     fake_exec = FakeExecution(FAKE_MONEY)
#     risk_manager = RiskManager(balance=FAKE_MONEY,
#                                max_percent_per_trade=max_percent_per_trade,
#                                daily_drawdown_limit_percent=daily_drawdown_limit_percent,
#                                max_concurrent_trades=max_concurrent_trades)
#
#     # Iterate over the selected crypto pairs
#     for pair in RISK_CONFIG['SELECTED_CRYPTO_PAIRS']:
#         print(f"\n--- Trading {pair} ---")
#
#         # Check for uptrend and decide whether to open a position
#         if predict_uptrend(pair):
#             # Calculate position size based on available balance
#             position_size = risk_manager.calculate_position_size('buy')
#             print(f"Position Size for {pair}: {position_size}")
#
#             # Execute the trade
#             fake_exec.execute_trade('buy', pair, position_size, 100)  # Example price
#         else:
#             print(f"No opportunity found for {pair}")
#
#
# if __name__ == "__main__":
#     run_trading_bot()

import time
from strategies.uptrend_prediction import predict_uptrend
from utils.data_ingestion        import get_selected_crypto_data
from utils.execution             import FakeExecution
from utils.risk_management       import RiskManager
from config.configs              import FAKE_MONEY, RISK_CONFIG
from utils.update_pairs import main

THRESHOLD_SCORE = 60          # anything below is ignored
MAX_PER_SCAN    = None
COOLDOWN_SEC = 3600          # 1-hour lockout
# ------------------------------------------------------------------
# 1) fetch once and decide which pairs to buy
# ------------------------------------------------------------------
# def scan_for_opportunities(fake_exec: FakeExecution,
#                            risk_mgr : RiskManager) -> None:
#     """Score all pairs, then open trades on the best ones first."""
#     market = get_selected_crypto_data()
#     prices = {p: df['close'].iloc[-1] for p, df in market.items()}
#
#     scored: list[tuple[float, str]] = []
#
#     # 1) score every pair
#     for pair in RISK_CONFIG['SELECTED_CRYPTO_PAIRS']:
#         print(f"\n--- Scoring {pair} ---")
#         score = predict_uptrend(pair)          # returns 0-100
#         scored.append((score, pair))
#
#     # 2) sort high→low
#     scored.sort(reverse=True)
#
#     # 3) open trades while allowed
#     opened = 0
#     for score, pair in scored:
#         if score < THRESHOLD_SCORE:
#             break                               # remaining scores lower
#
#         if risk_mgr.max_concurrent_reached(fake_exec):
#             print("Risk cap reached; no more positions this scan.")
#             break
#
#         if MAX_PER_SCAN and opened >= MAX_PER_SCAN:
#             break
#
#         size_usdt = risk_mgr.calculate_position_size('buy')
#         if size_usdt <= 0:
#             print("Size zero (insufficient balance); skipping.")
#             continue
#
#         price = prices[pair]
#         print(f"OPEN  {pair}  score={score:.0f}  stake={size_usdt:.2f} USDT  @ {price}")
#         fake_exec.execute_trade('buy', pair, size_usdt, price)
#         opened += 1
#
#     if opened == 0:
#         print("No opportunities met the threshold this scan.")

def scan_for_opportunities(fake_exec: FakeExecution,
                           risk_mgr : RiskManager) -> None:
    """
    Score every pair, sort high→low, then open trades from the top
    until the score drops below THRESHOLD_SCORE or the risk cap is hit.
    """
    market = get_selected_crypto_data()
    prices = {p: df['close'].iloc[-1] for p, df in market.items()}

    # 1) get scores for all pairs
    scored = []
    for pair in RISK_CONFIG['SELECTED_CRYPTO_PAIRS']:
        if fake_exec.recently_traded(pair, COOLDOWN_SEC):
            print(f"Skip {pair}: traded within last hour.")
            continue

        print(f"\n--- Scoring {pair} ---")
        s = predict_uptrend(pair)          # now returns an int 0–100
        scored.append((s, pair))

    # 2) sort by score descending
    scored.sort(reverse=True)

    # 3) iterate, opening trades while allowed
    for score, pair in scored:
        if score < THRESHOLD_SCORE:
            break    # lower scores follow – stop scanning

        if risk_mgr.max_concurrent_reached(fake_exec):
            print("Risk cap reached; no more entries this scan.")
            break

        stake_usdt = risk_mgr.calculate_position_size('buy')
        if stake_usdt <= 0:
            print("No free capital; skipping.")
            continue

        print(f"OPEN  {pair:12}  score={score:>3}  stake={stake_usdt:.2f} USDT")
        fake_exec.execute_trade('buy', pair, stake_usdt, prices[pair])


# ------------------------------------------------------------------
# 2) loop until everything you just opened is flat (targets hit)
# ------------------------------------------------------------------
def monitor_open_positions(fake_exec: FakeExecution,
                           poll_seconds: int = .5) -> None:
    """Keep checking prices; return only when every position is closed."""
    while True:
        if not fake_exec.has_open_positions():
            return                             # → all flat

        market  = get_selected_crypto_data()
        prices  = {p: df['close'].iloc[-1] for p, df in market.items()}

        # ---- NEW: show what we’re watching ------------------------------
        open_trades = fake_exec.get_open_positions()
        for t in open_trades:
            sym = t['symbol']
            print(f"Waiting → {sym}  price={prices[sym]}  target={t['target_price']}")
        # -----------------------------------------------------------------

        fake_exec.track_positions(prices)      # closes & beeps if hit
        time.sleep(0.5)



# ------------------------------------------------------------------
# 3) main control loop – alternates the two phases above
# ------------------------------------------------------------------
def run_trading_bot():
    risk_params = {k: RISK_CONFIG[k] for k in
                  ('max_percent_per_trade',
                   'daily_drawdown_limit_percent',
                   'max_concurrent_trades')}

    fake_exec  = FakeExecution(FAKE_MONEY)
    risk_mgr   = RiskManager(balance=FAKE_MONEY, **risk_params)

    while True:
        # -------- Phase A: look for new trades ------------
        scan_for_opportunities(fake_exec, risk_mgr)

        if not fake_exec.has_open_positions():
            print("No trades opened on this scan.")

        else:
            # -------- Phase B: babysit them until flat ----
            monitor_open_positions(fake_exec)

        # -------- Ask the trader what to do next ----------
        #resp = input("\nAll positions flat. Scan again? (yes/no): ").strip().lower()
        resp = 'yes'
        if resp != 'yes':
            print("Good-bye!")
            break
        else:
            #time.sleep(450)
            main()
            run_trading_bot()


if __name__ == "__main__":
    main()
    run_trading_bot()


