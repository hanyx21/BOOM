def generate_mean_reversion_signal(data):
    # Calculate the RSI
    delta = data['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    data['RSI'] = 100 - (100 / (1 + rs))

    # Debug: print the last few RSI values
    print(f"RSI: {data['RSI'].iloc[-1]}")

    # Adjusted Signal Conditions for more sensitivity
    if data['RSI'].iloc[-1] < 40:  # More aggressive buy threshold
        print("Signal: Buy (Oversold)")
        return 'buy'
    elif data['RSI'].iloc[-1] > 60:  # More aggressive sell threshold
        print("Signal: Sell (Overbought)")
        return 'sell'
    else:
        print("Signal: Hold (Neutral)")
        return 'hold'
