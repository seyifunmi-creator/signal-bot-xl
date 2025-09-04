import yfinance as yf
import pandas as pd
import numpy as np
import datetime

def generate_signals(pair):
    print(f"\nFetching data for {pair}...")
    try:
        df = yf.download(pair, period="1d", interval="1h")
    except Exception as e:
        return f"Error fetching data: {e}"

    # Check for empty or missing data
    if df is None or df.empty:
        return "No data available"

    # Calculate moving averages
    df['SMA_10'] = df['Close'].rolling(window=10).mean()
    df['SMA_20'] = df['Close'].rolling(window=20).mean()

    # Drop rows with NaN values in SMA columns (ensures clean latest row)
    df.dropna(subset=['SMA_10', 'SMA_20'], inplace=True)

    if df.empty:
        return "Insufficient data to generate signals"

    latest = df.iloc[-1]

    # Determine action safely
    if pd.isna(latest['SMA_10']) or pd.isna(latest['SMA_20']):
        return "Indicators not ready"

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
