import os
import psycopg2
import yfinance as yf
import pandas as pd
from datetime import datetime

# Database connection
DB_CONN = os.getenv('TIMESCALE_CONN')

# Connect to PostgreSQL
conn = psycopg2.connect(DB_CONN)
cur = conn.cursor()

# Predefined list of "best-known" symbols (can be customized)
symbols = ['BTC-USD', 'ETH-USD', 'SOL-USD', 'SPY', 'QQQ', 'AAPL', 'AMZN']

# Function to fetch data for each symbol and insert into the database
def fetch_and_insert_data(symbol, period='5d', interval='5m'):
    # Fetch historical data using Yahoo Finance
    data = yf.download(symbol, period=period, interval=interval)

    # Insert data into the database
    for idx, row in data.iterrows():
        ts = idx  # The timestamp (index of the row)
        open_price = float(row['Open'].iloc[0])  # Explicitly cast to float using .iloc[0]
        high_price = float(row['High'].iloc[0])  # Explicitly cast to float using .iloc[0]
        low_price = float(row['Low'].iloc[0])  # Explicitly cast to float using .iloc[0]
        close_price = float(row['Close'].iloc[0])  # Explicitly cast to float using .iloc[0]
        volume = int(row['Volume'].iloc[0])  # Explicitly cast to int using .iloc[0]

        # Insert the data into the market_data table
        cur.execute(
            """INSERT INTO market_data (symbol, ts, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, ts) DO NOTHING;""",
            (symbol, ts, open_price, high_price, low_price, close_price, volume)
        )

# Fetch and insert data for all predefined symbols
for symbol in symbols:
    fetch_and_insert_data(symbol)

# Commit and close the connection
conn.commit()
cur.close()
conn.close()
