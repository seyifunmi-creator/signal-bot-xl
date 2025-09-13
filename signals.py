import yfinance as yf
import pandas as pd

# === Signal Generation ===
def fetch_data(symbol, period="1d", interval="5m"):
    """
    Fetch OHLC data from Yahoo Finance.
    """
    try:
        data = yf.download(symbol, period=period, interval=interval, progress=False)
        if data.empty:
            return None
        return data
    except Exception as e:
        print(f"[ERROR] Failed to fetch data for {symbol}: {e}")
        return None

def calculate_indicators(data):
    """
    Add EMA and RSI indicators to dataframe.
    """
    data["EMA5"] = data["Close"].ewm(span=5, adjust=False).mean()
    data["EMA20"] = data["Close"].ewm(span=20, adjust=False).mean()

    # RSI
    delta = data["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    data["RSI"] = 100 - (100 / (1 + rs))

    return data

def generate_signal(symbol):
    """
    Generate buy/sell/hold signal based on EMA crossover + RSI filter.
    """
    data = fetch_data(symbol)
    if data is None:
        return None

    data = calculate_indicators(data)
    latest = data.iloc[-1]

    if latest["EMA5"] > latest["EMA20"] and latest["RSI"] > 50:
        return "BUY"
    elif latest["EMA5"] < latest["EMA20"] and latest["RSI"] < 50:
        return "SELL"
    else:
        return "HOLD"
