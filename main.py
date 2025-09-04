import yfinance as yf
import pandas as pd
import numpy as np

def fetch_data(symbol):
    try:
        data = yf.download(symbol, period="1d", interval="1h", auto_adjust=True)
        if data is None or data.empty:
            print(f"[!] No data available for {symbol}")
            return None
        return data
    except Exception as e:
        print(f"[!] Error fetching data for {symbol}: {e}")
        return None

def generate_signals(data):
    if data is None or data.empty:
        return None
    
    data['EMA_9'] = data['Close'].ewm(span=9, adjust=False).mean()
    data['EMA_21'] = data['Close'].ewm(span=21, adjust=False).mean()
    
    latest = data.iloc[-1]
    signal = "HOLD"

    if pd.notna(latest['EMA_9']) and pd.notna(latest['EMA_21']):
        if latest['EMA_9'] > latest['EMA_21']:
            signal = "BUY"
        elif latest['EMA_9'] < latest['EMA_21']:
            signal = "SELL"

    if pd.notna(latest['Close']):
        if signal == "BUY":
            tp1 = round(latest['Close'] * 1.001, 3)
            tp2 = round(latest['Close'] * 1.002, 3)
            tp3 = round(latest['Close'] * 1.003, 3)
            tp4 = round(latest['Close'] * 1.004, 3)
            sl = round(latest['Close'] * 0.998, 3)
        elif signal == "SELL":
            tp1 = round(latest['Close'] * 0.999, 3)
            tp2 = round(latest['Close'] * 0.998, 3)
            tp3 = round(latest['Close'] * 0.997, 3)
            tp4 = round(latest['Close'] * 0.996, 3)
            sl = round(latest['Close'] * 1.002, 3)
        else:
            tp1 = tp2 = tp3 = tp4 = sl = "N/A"
    else:
        tp1 = tp2 = tp3 = tp4 = sl = "N/A"

    return {
        "signal": signal,
        "TP1": tp1,
        "TP2": tp2,
        "TP3": tp3,
        "TP4": tp4,
        "SL": sl
    }

def main():
    print("\nSignal Bot XL initialized")
    print("\nMode: Signals Only (TP1–TP4 + SL)")
    print("Pairs: XAU/USD, EUR/USD, GBP/USD, USD/JPY, USD/CAD\n")

    pairs = {
        "XAU/USD": "GC=F",
        "EUR/USD": "EURUSD=X",
        "GBP/USD": "GBPUSD=X",
        "USD/JPY": "USDJPY=X",
        "USD/CAD": "USDCAD=X"
    }

    for pair_name, symbol in pairs.items():
        print(f"Fetching data for {symbol}...")
        data = fetch_data(symbol)
        signals = generate_signals(data)

        if signals:
            print(f"\n{pair_name} Signals:")
            print(f"Signal: {signals['signal']}")
            print(f"TP1: {signals['TP1']}")
            print(f"TP2: {signals['TP2']}")
            print(f"TP3: {signals['TP3']}")
            print(f"TP4: {signals['TP4']}")
            print(f"SL: {signals['SL']}\n")
        else:
            print(f"\n{pair_name} Signals: No data available\n")

    input("\nPress Enter to close the program...")

if __name__ == "__main__":
    main()
