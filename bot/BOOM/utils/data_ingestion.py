import ccxt
import pandas as pd
from config.configs import SELECTED_CRYPTO_PAIRS

# Initialize exchange (Binance in this case)
exchange = ccxt.binance()

def fetch_crypto_data(symbol: str, timeframe='1h', limit=200) -> pd.DataFrame:
    """Fetch market data for the given symbol."""
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    data = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    data['timestamp'] = pd.to_datetime(data['timestamp'], unit='ms')
    return data

def get_selected_crypto_data() -> dict:
    """Fetch data for all selected crypto pairs."""
    all_data = {}
    for pair in SELECTED_CRYPTO_PAIRS:
        data = fetch_crypto_data(pair)
        all_data[pair] = data
    return all_data
