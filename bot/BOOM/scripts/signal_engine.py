# import os
# import psycopg2
# import pandas as pd
# import talib as ta
# import yfinance as yf
# from datetime import datetime
#
# # Database connection
# DB_CONN = os.getenv('TIMESCALE_CONN')
#
# # Connect to PostgreSQL
# conn = psycopg2.connect(DB_CONN)
# cur = conn.cursor()
#
# # Fetch data from TimescaleDB (PostgreSQL)
# cur.execute("SELECT ts, open, high, low, close, volume FROM market_data WHERE symbol = 'SPY' ORDER BY ts DESC LIMIT 1000;")
# data = cur.fetchall()
#
# # Convert data into pandas DataFrame
# df = pd.DataFrame(data, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
# df['ts'] = pd.to_datetime(df['ts'])  # Convert timestamp to datetime format
#
# # Calculate Indicators
# # Trend-following: Moving Averages and MACD
# df['50_SMA'] = ta.SMA(df['close'], timeperiod=50)
# df['200_SMA'] = ta.SMA(df['close'], timeperiod=200)
# df['MACD'], df['MACD_signal'], df['MACD_hist'] = ta.MACD(df['close'], fastperiod=12, slowperiod=26, signalperiod=9)
#
# # Mean Reversion: RSI
# df['RSI'] = ta.RSI(df['close'], timeperiod=14)
#
# # Statistical Arbitrage: Pair Trading (SPY vs QQQ)
# # Fetch QQQ data
# qqq_data = yf.download('QQQ', period='5d', interval='5m')
# df['qqq_close'] = qqq_data['Close']
#
# # Calculate the spread between SPY and QQQ
# df['spread'] = df['close'] - df['qqq_close']
# df['spread_mean'] = df['spread'].rolling(window=100).mean()
# df['spread_std'] = df['spread'].rolling(window=100).std()
#
# # Trading signals
# df['signal'] = 0  # Default: No Signal
# df.loc[(df['50_SMA'] > df['200_SMA']) & (df['MACD'] > df['MACD_signal']) & (df['RSI'] < 30), 'signal'] = 1  # Buy Signal
# df.loc[(df['50_SMA'] < df['200_SMA']) & (df['MACD'] < df['MACD_signal']) & (df['RSI'] > 70), 'signal'] = -1  # Sell Signal
#
# # Statistical Arbitrage: If spread exceeds 2 standard deviations, trade
# threshold = 2
# df.loc[df['spread'] > df['spread_mean'] + threshold * df['spread_std'], 'signal'] = -1  # Sell SPY, Buy QQQ
# df.loc[df['spread'] < df['spread_mean'] - threshold * df['spread_std'], 'signal'] = 1   # Buy SPY, Sell QQQ
#
# # Insert signals into PostgreSQL (or TimescaleDB)
# for idx, row in df.iterrows():
#     ts = row['ts']
#     signal = row['signal']
#     cur.execute(
#         """INSERT INTO trade_signals (symbol, ts, signal)
#         VALUES (%s, %s, %s)
#         ON CONFLICT DO NOTHING;""",
#         ('SPY', ts, signal)
#     )
#
# # Commit and close connection
# conn.commit()
# cur.close()
# conn.close()
import os
import psycopg2
import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime

# Database connection
DB_CONN = os.getenv('TIMESCALE_CONN')

# Connect to PostgreSQL
conn = psycopg2.connect(DB_CONN)
cur = conn.cursor()

# Fetch data from TimescaleDB (PostgreSQL)
cur.execute("SELECT ts, open, high, low, close, volume FROM market_data ORDER BY ts DESC ;")
data = cur.fetchall()

# Convert data into pandas DataFrame
df = pd.DataFrame(data, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
df['ts'] = pd.to_datetime(df['ts'])  # Convert timestamp to datetime format

# --- Trend-following Indicators ---
# 50-period and 200-period Simple Moving Averages (SMA)
df['50_SMA'] = df['close'].rolling(window=50).mean()
df['200_SMA'] = df['close'].rolling(window=200).mean()

# MACD (Moving Average Convergence Divergence)
df['EMA_12'] = df['close'].ewm(span=12, min_periods=1).mean()
df['EMA_26'] = df['close'].ewm(span=26, min_periods=1).mean()
df['MACD'] = df['EMA_12'] - df['EMA_26']
df['MACD_signal'] = df['MACD'].ewm(span=9, min_periods=1).mean()  # Signal line

# --- Mean Reversion Indicator ---
# RSI (Relative Strength Index) calculation
delta = df['close'].diff()
gain = delta.where(delta > 0, 0)
loss = -delta.where(delta < 0, 0)

avg_gain = gain.rolling(window=14, min_periods=1).mean()
avg_loss = loss.rolling(window=14, min_periods=1).mean()

rs = avg_gain / avg_loss
df['RSI'] = 100 - (100 / (1 + rs))

# --- Statistical Arbitrage (Pair Trading) ---
# Fetch QQQ data for pair trading
qqq_data = yf.download('QQQ', period='5d', interval='5m')
df['qqq_close'] = qqq_data['Close']

# Calculate the spread between SPY and QQQ
df['spread'] = df['close'] - df['qqq_close']
df['spread_mean'] = df['spread'].rolling(window=100).mean()
df['spread_std'] = df['spread'].rolling(window=100).std()

# --- Trading Signals ---
# Trend-following signals:
df['signal'] = 0  # Default: No Signal
df.loc[(df['50_SMA'] > df['200_SMA']) & (df['MACD'] > df['MACD_signal']) & (df['RSI'] < 30), 'signal'] = 1  # Buy Signal
df.loc[(df['50_SMA'] < df['200_SMA']) & (df['MACD'] < df['MACD_signal']) & (df['RSI'] > 70), 'signal'] = -1  # Sell Signal

# Statistical Arbitrage: If spread exceeds 2 standard deviations, trade
threshold = 2
df.loc[df['spread'] > df['spread_mean'] + threshold * df['spread_std'], 'signal'] = -1  # Sell SPY, Buy QQQ
df.loc[df['spread'] < df['spread_mean'] - threshold * df['spread_std'], 'signal'] = 1   # Buy SPY, Sell QQQ

# Insert signals into PostgreSQL (or TimescaleDB)
for idx, row in df.iterrows():
    ts = row['ts']
    signal = row['signal']
    cur.execute(
        """INSERT INTO trade_signals (symbol, ts, signal)
        VALUES (%s, %s, %s)
        ON CONFLICT DO NOTHING;""",
        ('SPY', ts, signal)
    )

# Commit and close connection
conn.commit()
cur.close()
conn.close()
