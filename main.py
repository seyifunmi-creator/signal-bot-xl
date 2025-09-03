
# main.py
# Signal Bot XL - Live single-run signal generator for 5 pairs
# Strategy: MA crossover (20 / 50) + RSI confirmation; TP levels by ATR multiples

import sys
import time
from datetime import datetime
import numpy as np
import pandas as pd

# yfinance is used to fetch live quotes (no API key required)
# pip install yfinance pandas numpy
import yfinance as yf

PAIRS = {
    "XAU/USD": "XAUUSD=X",   # Gold
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",      # yfinance uses "JPY=X" for USD/JPY quotes (base USD)
    "USD/CAD": "CAD=X",      # yfinance uses "CAD=X" for USD/CAD quotes (base USD)
}

# Configurable parameters
SHORT_MA = 20
LONG_MA = 50
RSI_PERIOD = 14
ATR_PERIOD = 14
INTERVAL = "5m"     # try '5m' or '15m' or '1h' depending on availability
PERIOD = "7d"       # how much history to attempt to download (yfinance limitations for small intervals)

def fetch_ohlc(ticker, interval=INTERVAL, period=PERIOD):
    """Fetch OHLC data with yfinance. Returns DataFrame with columns: Open, High, Low, Close, Volume"""
    try:
        data = yf.download(tickers=ticker, period=period, interval=interval, progress=False, threads=False)
        if data is None or data.empty:
            # try different period/interval fallbacks
            data = yf.download(tickers=ticker, period="30d", interval="1h", progress=False, threads=False)
        return data
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return pd.DataFrame()

def compute_rsi(close, period=RSI_PERIOD):
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    # Wilder smoothing
    ema_up = up.ewm(alpha=1/period, adjust=False).mean()
    ema_down = down.ewm(alpha=1/period, adjust=False).mean()
    rs = ema_up / (ema_down + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def compute_atr(df, period=ATR_PERIOD):
    high = df['High']
    low = df['Low']
    close = df['Close']
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr

def signal_for_pair(df):
    """Return dict with signal info or None if not enough data."""
    if df.shape[0] < max(LONG_MA, RSI_PERIOD, ATR_PERIOD) + 5:
        return None

    close = df['Close']
    short_ma = close.rolling(window=SHORT_MA).mean()
    long_ma = close.rolling(window=LONG_MA).mean()
    rsi = compute_rsi(close)
    atr = compute_atr(df)

    latest = df.iloc[-1]
    latest_close = latest['Close']

    sma_short = short_ma.iloc[-1]
    sma_long = long_ma.iloc[-1]
    rsi_latest = rsi.iloc[-1]
    atr_latest = atr.iloc[-1]

    # Basic MA crossover rule
    # buy condition: short_ma > long_ma and previous short_ma <= previous long_ma
    prev_short = short_ma.iloc[-2]
    prev_long = long_ma.iloc[-2]

    signal = "NO SIGNAL"
    reason = ""
    if np.isnan([sma_short, sma_long, prev_short, prev_long, rsi_latest, atr_latest]).any():
        return None

    # Crossover detection
    if (prev_short <= prev_long) and (sma_short > sma_long):
        # potential BUY; confirm with RSI not overbought
        if rsi_latest < 70:
            signal = "BUY"
            reason = f"MA Crossover + RSI {rsi_latest:.1f}"
    elif (prev_short >= prev_long) and (sma_short < sma_long):
        # potential SELL; confirm with RSI not oversold
        if rsi_latest > 30:
            signal = "SELL"
            reason = f"MA Crossover + RSI {rsi_latest:.1f}"

    # Generate TP/SL using ATR multiples
    # For BUY: TP levels above price; for SELL: TP levels below price
    # Use ATR as volatility gauge; if atr is very small, fallback to percentage
    if atr_latest <= 0 or np.isnan(atr_latest):
        atr_latest = max(0.0005 * latest_close, 0.01)  # fallback

    # define multipliers
    tp_multipliers = [1.0, 1.8, 2.6, 3.5]  # multiples of ATR
    sl_multiplier = 1.0  # 1 ATR for SL

    tps = []
    sl = None
    if signal == "BUY":
        for m in tp_multipliers:
            tps.append(latest_close + m * atr_latest)
        sl = latest_close - sl_multiplier * atr_latest
    elif signal == "SELL":
        for m in tp_multipliers:
            tps.append(latest_close - m * atr_latest)
        sl = latest_close + sl_multiplier * atr_latest

    return {
        "signal": signal,
        "reason": reason,
        "price": latest_close,
        "rsi": rsi_latest,
        "atr": atr_latest,
        "tps": tps,
        "sl": sl,
        "short_ma": sma_short,
        "long_ma": sma_long
    }

def pretty_print(pair_name, info):
    if info is None:
        print(f"{pair_name}: insufficient data or fetch error.\n")
        return
    sig = info['signal']
    print(f"=== {pair_name} ===")
    if sig == "NO SIGNAL":
        print("Signal: NO SIGNAL\n")
        return
    print(f"Signal: {sig}  |  Price: {info['price']:.5f}  |  RSI: {info['rsi']:.1f}  |  ATR: {info['atr']:.5f}")
    print(f"Reason: {info['reason']}")
    tps = info['tps']
    # Format TPs nicely:
    for i, tp in enumerate(tps, start=1):
        print(f"TP{i}: {tp:.5f}")
    print(f"SL : {info['sl']:.5f}\n")

def main():
    print("Signal Bot XL initialized\n")
    print("Mode: Signals Only (TP1-TP4 + SL)\n")
    print("Pairs: " + ", ".join(PAIRS.keys()) + "\n")

    for pair_name, ticker in PAIRS.items():
        print(f"Fetching {pair_name}...")
        df = fetch_ohlc(ticker)
        if df is None or df.empty:
            print(f"Could not fetch data for {pair_name}.")
            continue

        info = signal_for_pair(df)
        pretty_print(pair_name, info)
        # small pause to avoid rate issues
        time.sleep(0.5)

    print("Finished generating live signals.")
    input("\nPress Enter to close the program...")

if _name_ == "_main_":
    main()
input("\nPress Enter to close the program...")
