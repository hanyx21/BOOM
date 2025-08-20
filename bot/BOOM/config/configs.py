import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env

# General Settings
FAKE_MONEY = float(os.getenv('FAKE_MONEY', 1500))  # Starting balance for paper trading
TARGET_PERCENTAGE = 0.35  # Target price increase (0.2%)
MAX_PERCENT_PER_TRADE = 1  # Maximum position size (5% of current balance)
DAILY_DRAWDOWN_LIMIT = 5.0  # Daily drawdown limit (5%)
MAX_CONCURRENT_TRADES = 1  # Max number of concurrent trades

# Trading Pairs to Monitor (ensure this is correctly loaded)
SELECTED_CRYPTO_PAIRS = os.getenv("SELECTED_CRYPTO_PAIRS", "BTC/USDT,ETH/USDT,ADA/USDT,IMX/USDT").split(",")

# Risk Management Settings
RISK_CONFIG = {
    "max_percent_per_trade": MAX_PERCENT_PER_TRADE,
    "daily_drawdown_limit_percent": DAILY_DRAWDOWN_LIMIT,
    "max_concurrent_trades": MAX_CONCURRENT_TRADES,
    "SELECTED_CRYPTO_PAIRS": SELECTED_CRYPTO_PAIRS
}


