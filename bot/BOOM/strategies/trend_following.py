def generate_trend_signal(data):
    # Calculate the 50-period and 200-period SMAs
    data['SMA50'] = data['close'].rolling(window=50).mean()

    # Check if there are enough data points for SMA200 (rolling window)
    if len(data) >= 200:
        data['SMA200'] = data['close'].rolling(window=200).mean()
    else:
        data['SMA200'] = None  # Set to None if not enough data points

    # Calculate MACD
    data['MACD'] = data['close'].ewm(span=12).mean() - data['close'].ewm(span=26).mean()
    data['MACD_signal'] = data['MACD'].ewm(span=9).mean()

    # Debug: print last few values of SMA and MACD
    print(f"SMA50: {data['SMA50'].iloc[-1]}, SMA200: {data['SMA200'].iloc[-1] if len(data) >= 200 else 'N/A'}")
    print(f"MACD: {data['MACD'].iloc[-1]}, MACD_signal: {data['MACD_signal'].iloc[-1]}")

    # Signal conditions
    if data['SMA50'].iloc[-1] > data['SMA200'].iloc[-1] and data['MACD'].iloc[-1] > data['MACD_signal'].iloc[-1]:
        print("Signal: Buy")
        return 'buy'
    elif data['SMA50'].iloc[-1] < data['SMA200'].iloc[-1] and data['MACD'].iloc[-1] < data['MACD_signal'].iloc[-1]:
        print("Signal: Sell")
        return 'sell'
    else:
        print("Signal: Hold")
        return 'hold'
