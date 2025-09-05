import yfinance as yf
import pandas as pd
import numpy as np

def generate_signals(pair):
    print(f"\nFetching data for {pair}...")

    # Step 1: Initial fetch (1 month)
    try:
        df = yf.download(pair, period="1mo", interval="1h")
    except Exception as e:
        return f"Error fetching data: {e}"

    # Step 2: Fallback if data too small
    if df is None or df.empty or len(df) < 50:
        print(f"Not enough data for {pair}, retrying with larger period...")
        try:
            df = yf.download(pair, period="3mo", interval="1h")
        except Exception as e:
            return f"Error fetching extended data: {e}"

    if df is None or df.empty or len(df) < 50:
        return "No sufficient data available"

    # Indicators
    df['SMA_10'] = df['Close'].rolling(window=10).mean()
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
    df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = df['EMA_12'] - df['EMA_26']
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['RSI'] = 100 - (100 / (1 + df['Close'].pct_change().add(1).rolling(14).apply(lambda x: (x > 0).sum() / max(1, (x < 0).sum()))))

    df = df.dropna()
    if df.empty:
        return "No sufficient data after cleaning"

    latest = df.iloc[-1].copy()

    trend_up = float(latest['SMA_10']) > float(latest['SMA_20'])
    trend_down = float(latest['SMA_10']) < float(latest['SMA_20'])
    macd_cross_up = float(latest['MACD']) > float(latest['Signal'])
    macd_cross_down = float(latest['MACD']) < float(latest['Signal'])
    rsi_ok_long = float(latest['RSI']) < 70
    rsi_ok_short = float(latest['RSI']) > 30

    # Decision logic
    action = "HOLD"
    reasons = []

    if trend_up and macd_cross_up and rsi_ok_long:
        action = "BUY"
        reasons.append("Strong Long: trend_up+MACD_up+RSI_ok")
    elif trend_down and macd_cross_down and rsi_ok_short:
        action = "SELL"
        reasons.append("Strong Short: trend_down+MACD_down+RSI_ok")
    else:
        reasons.append("No high-confidence confluence")

    price = latest['Close']
    tp1 = round(price * (1.001 if action == "BUY" else 0.999), 3)
    tp2 = round(price * (1.002 if action == "BUY" else 0.998), 3)
    tp3 = round(price * (1.003 if action == "BUY" else 0.997), 3)
    sl = round(price * (0.997 if action == "BUY" else 1.003), 3)

    return f"{action} @ {price}\nTP1: {tp1}, TP2: {tp2}, TP3: {tp3}, SL: {sl}\nReasons: {', '.join(reasons)}"


def main():
    print("Signal Bot XL initialized")
    print("Mode: Precision-Focused Signals (TP1–TP3 + SL)")
    print("Pairs: XAU/USD, EUR/USD, GBP/USD, USD/JPY, USD/CAD")

    pairs = ["GC=F", "EURUSD=X", "GBPUSD=X", "JPY=X", "CAD=X"]

    for pair in pairs:
        signals = generate_signals(pair)
        print(f"\n{pair} Signals:\n{signals}")

    input("\nPress Enter to close the program...")


if __name__ == "__main__":
    main()
