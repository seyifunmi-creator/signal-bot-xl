import yfinance as yf
import pandas as pd
import numpy as np

def fetch_data(pair):
    """
    Fetch recent forex data for the given pair.
    Adjust period/interval as needed.
    """
    print(f"Fetching data for {pair}...")
    data = yf.download(pair, period="1d", interval="15m")
    return data

def generate_signals(data):
    """
    Generates trade signals based on a simple moving average crossover
    and recent volatility for dynamic TP and SL.
    """
    if data.empty:
        return "No data available"

    data["SMA_fast"] = data["Close"].rolling(window=5).mean()
    data["SMA_slow"] = data["Close"].rolling(window=20).mean()
    last_row = data.iloc[-1]

    # Calculate recent volatility (average candle size over last 10 bars)
    volatility = data["High"][-10:].mean() - data["Low"][-10:].mean()
    tp_step = round(volatility * 0.5, 2)  # half the volatility per TP
    sl_step = round(volatility, 2)        # full volatility for stop loss

    if last_row["SMA_fast"] > last_row["SMA_slow"]:
        direction = "BUY"
        tps = [f"+{tp_step*(i+1)} pips" for i in range(4)]
        sl = f"-{sl_step} pips"
    else:
        direction = "SELL"
        tps = [f"-{tp_step*(i+1)} pips" for i in range(4)]
        sl = f"+{sl_step} pips"

    return {
        "Direction": direction,
        "TP1": tps[0],
        "TP2": tps[1],
        "TP3": tps[2],
        "TP4": tps[3],
        "SL": sl
    }

def main():
    print("\nSignal Bot XL initialized\n")
    print("Mode: Signals Only (TP1–TP4 + SL)")
    print("Pairs: XAU/USD, EUR/USD, GBP/USD, USD/JPY, USD/CAD\n")

    pairs = {
        "XAU/USD": "XAUUSD=X",
        "EUR/USD": "EURUSD=X",
        "GBP/USD": "GBPUSD=X",
        "USD/JPY": "USDJPY=X",
        "USD/CAD": "USDCAD=X"
    }

    for name, symbol in pairs.items():
        data = fetch_data(symbol)
        signals = generate_signals(data)
        print(f"\n{name} Signals: {signals}")

    input("\nPress Enter to close the program...")

if __name__ == "__main__":
    main()
