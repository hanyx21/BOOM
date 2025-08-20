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

# Fetch data from TimescaleDB (PostgreSQL) for all symbols
cur.execute("SELECT symbol, ts, open, high, low, close, volume FROM market_data ORDER BY symbol, ts DESC;")
data = cur.fetchall()

# Convert data into pandas DataFrame
df = pd.DataFrame(data, columns=['symbol', 'ts', 'open', 'high', 'low', 'close', 'volume'])
df['ts'] = pd.to_datetime(df['ts'])  # Convert timestamp to datetime format

# --- Ensure 'symbol' column exists ---
if 'symbol' not in df.columns:
    raise KeyError("'symbol' column not found in the DataFrame")

# --- Trend-following Indicators ---
# 50-period and 200-period Simple Moving Averages (SMA)
df['50_SMA'] = df.groupby('symbol')['close'].rolling(window=50, min_periods=1).mean().reset_index(level=0, drop=True)
df['200_SMA'] = df.groupby('symbol')['close'].rolling(window=200, min_periods=1).mean().reset_index(level=0, drop=True)

# MACD (Moving Average Convergence Divergence)
df['EMA_12'] = df.groupby('symbol')['close'].ewm(span=12, min_periods=1).mean().reset_index(level=0, drop=True)
df['EMA_26'] = df.groupby('symbol')['close'].ewm(span=26, min_periods=1).mean().reset_index(level=0, drop=True)
df['MACD'] = df['EMA_12'] - df['EMA_26']
df['MACD_signal'] = df.groupby('symbol')['MACD'].ewm(span=9, min_periods=1).mean().reset_index(level=0, drop=True)

# --- Mean Reversion Indicator ---
# RSI (Relative Strength Index) calculation
delta = df.groupby('symbol')['close'].diff()
gain = delta.where(delta > 0, 0)
loss = -delta.where(delta < 0, 0)

avg_gain = gain.groupby('symbol').rolling(window=14, min_periods=1).mean().reset_index(level=0, drop=True)
avg_loss = loss.groupby('symbol').rolling(window=14, min_periods=1).mean().reset_index(level=0, drop=True)

rs = avg_gain / avg_loss
df['RSI'] = 100 - (100 / (1 + rs))

# --- Statistical Arbitrage (Pair Trading) ---
# Fetch QQQ data for pair trading
qqq_data = yf.download('QQQ', period='5d', interval='5m')
df['qqq_close'] = qqq_data['Close']

# Calculate the spread between SPY and QQQ
df['spread'] = df['close'] - df['qqq_close']
df['spread_mean'] = df.groupby('symbol')['spread'].rolling(window=100).mean().reset_index(level=0, drop=True)
df['spread_std'] = df.groupby('symbol')['spread'].rolling(window=100).std().reset_index(level=0, drop=True)

# --- Simulated Trading Logic ---
initial_capital = 1500  # Starting capital for simulation
capital = initial_capital  # Capital during simulation
position = 0  # No position initially
portfolio = []  # To track the portfolio value over time
trades = []  # Track buy/sell signals and positions

# Create a signal to track positions
df['signal'] = 0  # Default: No Signal
df.loc[(df['50_SMA'] > df['200_SMA']) & (df['MACD'] > df['MACD_signal']) & (df['RSI'] < 30), 'signal'] = 1  # Buy Signal
df.loc[(df['50_SMA'] < df['200_SMA']) & (df['MACD'] < df['MACD_signal']) & (df['RSI'] > 70), 'signal'] = -1  # Sell Signal

# Simulate trading: Execute buy/sell based on signals
for idx, row in df.iterrows():
    signal = row['signal']
    price = row['close']

    # Buy signal: Enter position if not already in position
    if signal == 1 and position == 0:
        position = capital / price  # Buy as much as we can with the available capital
        capital = 0  # Capital is now 0 as it's fully invested in the position
        trades.append(('BUY', row['ts'], price))

    # Sell signal: Exit position if already in position
    elif signal == -1 and position > 0:
        capital = position * price  # Sell the position and convert it back to cash
        position = 0  # Exit the position
        trades.append(('SELL', row['ts'], price))

    # Track portfolio value
    portfolio_value = capital + (position * price)  # Total value = cash + position value
    portfolio.append((row['ts'], portfolio_value))  # Track portfolio value over time

# Convert portfolio into DataFrame for analysis
portfolio_df = pd.DataFrame(portfolio, columns=['ts', 'portfolio_value'])
portfolio_df.set_index('ts', inplace=True)

# --- Performance Metrics ---
total_return = (portfolio_df['portfolio_value'].iloc[-1] - initial_capital) / initial_capital * 100
max_drawdown = (portfolio_df['portfolio_value'].min() - portfolio_df['portfolio_value'].max()) / portfolio_df['portfolio_value'].max() * 100

# Print out the results
print(f"Total Return: {total_return:.2f}%")
print(f"Max Drawdown: {max_drawdown:.2f}%")
print(f"Number of Trades: {len(trades)}")
for trade in trades:
    print(f"{trade[0]} on {trade[1]} at price {trade[2]}")

# Commit and close connection
conn.commit()
cur.close()
conn.close()
