import yfinance as yf
import pandas as pd
import numpy as np
import datetime

def generate_signals(pair):
    print(f"\nFetching data for {pair}...")

    periods_to_try = ["1d", "5d", "1mo"]
    df = None

    # Step 1: Try multiple periods until enough data is found
    for period in periods_to_try:
        try:
            df = yf.download(pair, period=period, interval="1h", auto_adjust=True)
        except Exception as e:
            return f"Error fetching data: {e}"

        if df is not None and len(df) >= 20:
            print(f"Using data period: {period}")
            break

    # Step 2: Validate data
    if df is None or df.empty or len(df) < 20:
        return "Not enough data to generate signals"

    # Step 3: Ensure 'Close' column exists
    if 'Close' not in df.columns:
        return "No close price data available"

    # Step 4: Calculate moving averages safely
    df['SMA_10'] = df['Close'].rolling(window=10).mean()
    df['SMA_20'] = df['Close'].rolling(window=20).mean()

    if 'SMA_10' not in df.columns or 'SMA_20' not in df.columns:
        return "Indicators could not be calculated"

    df = df.dropna(subset=['SMA_10', 'SMA_20'])
    if df.empty:
        return "Indicators not ready"

    # Step 5: Get the latest row
    latest = df.iloc[-1]

    # Step 6: Check for NaN values in latest indicators
    if pd.isna(latest['SMA_10']) or pd.isna(latest['SMA_20']):
        return "Indicators not ready"

    # Step 7: Determine action
    if latest['SMA_10'] > latest['SMA_20']:
        action = "BUY"
    elif latest['SMA_10'] < latest['SMA_20']:
        action = "SELL"
    else:
        action = "HOLD"

    price = latest['Close']
    tp1 = round(price * (1.001 if action == "BUY" else 0.999), 3)
    tp2 = round(price * (1.002 if action == "BUY" else 0.998), 3)
    tp3 = round(price * (1.003 if action == "BUY" else 0.997), 3)
    sl = round(price * (0.997 if action == "BUY" else 1.003), 3)

    return f"{action} @ {price}\nTP1: {tp1}, TP2: {tp2}, TP3: {tp3}, SL: {sl}"

def main():
    print("Signal Bot XL initialized")
    print("Mode: Signals Only (TP1–TP3 + SL)")
    print("Pairs: XAU/USD, EUR/USD, GBP/USD, USD/JPY, USD/CAD")

    pairs = ["GC=F", "EURUSD=X", "GBPUSD=X", "JPY=X", "CAD=X"]

    for pair in pairs:
        signals = generate_signals(pair)
        print(f"\n{pair} Signals:\n{signals}")

    input("\nPress Enter to close the program...")

if __name__ == "__main__":
    main()
