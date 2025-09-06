# main.py
import yfinance as yf
import pandas as pd
import numpy as np

# ---------------- PARAMETERS ----------------
instruments = ["GC=F", "EURUSD=X", "GBPUSD=X", "JPY=X", "CAD=X"]
RSI_PERIOD = 14
PERIOD = "1y"
INTERVAL = "1h"

# ---------------- PER-INSTRUMENT SETTINGS ----------------
instrument_params = {
    "GC=F": {"SMA_SHORT":9, "SMA_LONG":28, "TP1":0.004, "TP2":0.008, "TP3":0.012},
    "EURUSD=X": {"SMA_SHORT":10, "SMA_LONG":30, "TP1":0.005, "TP2":0.01, "TP3":0.015},
    "GBPUSD=X": {"SMA_SHORT":9, "SMA_LONG":28, "TP1":0.0045, "TP2":0.009, "TP3":0.0135},
    "JPY=X": {"SMA_SHORT":10, "SMA_LONG":32, "TP1":0.0035, "TP2":0.007, "TP3":0.01},
    "CAD=X": {"SMA_SHORT":9, "SMA_LONG":30, "TP1":0.004, "TP2":0.008, "TP3":0.012}
}

# ---------------- RSI CALCULATION ----------------
def calculate_rsi(df, period=14):
    delta = df['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# ---------------- BACKTEST FUNCTION ----------------
def backtest_instrument(symbol):
    print(f"\n--- Backtesting {symbol} ---")
    df = yf.download(symbol, period=PERIOD, interval=INTERVAL, auto_adjust=True)
    if df.empty:
        print(f"No data for {symbol}")
        return

    params = instrument_params[symbol]
    SMA_SHORT = params["SMA_SHORT"]
    SMA_LONG = params["SMA_LONG"]
    TP1 = params["TP1"]
    TP2 = params["TP2"]
    TP3 = params["TP3"]

    # Calculate SMAs and RSI
    df['SMA_SHORT'] = df['Close'].rolling(SMA_SHORT).mean()
    df['SMA_LONG'] = df['Close'].rolling(SMA_LONG).mean()
    df['RSI'] = calculate_rsi(df, RSI_PERIOD)

    trades = []
    position = None
    entry_price = 0
    tp_hits = [0,0,0]
    tp_flags = [False, False, False]
    cumulative_profit = 0

    for i in range(len(df)):
        latest = df.iloc[i:i+1]  # 1-row DataFrame to avoid Series issues

        price = latest['Close'].iloc[0] if not latest['Close'].isna().all() else np.nan
        sma_short = latest['SMA_SHORT'].iloc[0] if not latest['SMA_SHORT'].isna().all() else np.nan
        sma_long = latest['SMA_LONG'].iloc[0] if not latest['SMA_LONG'].isna().all() else np.nan
        rsi = latest['RSI'].iloc[0] if not latest['RSI'].isna().all() else np.nan

        if np.isnan(price) or np.isnan(sma_short) or np.isnan(sma_long) or np.isnan(rsi):
            signal = "HOLD"
        elif sma_short > sma_long and rsi < 70:
            signal = "BUY"
        elif sma_short < sma_long and rsi > 30:
            signal = "SELL"
        else:
            signal = "HOLD"

        # Open BUY
        if signal == "BUY" and position != "BUY":
            position = "BUY"
            entry_price = price
            trades.append({'type':'BUY','entry':entry_price,'exit':None,'profit':0})
            tp_flags = [False, False, False]
            print(f"OPEN BUY at {entry_price:.2f}")

        # Check TPs
        if position == "BUY":
            tp_levels = [entry_price*(1+TP1), entry_price*(1+TP2), entry_price*(1+TP3)]
            for j in range(3):
                if price >= tp_levels[j] and not tp_flags[j]:
                    tp_hits[j] += 1
                    tp_flags[j] = True
                    print(f"HIT TP{j+1} at {price:.2f}")

        # Close on SELL
        if signal == "SELL" and position == "BUY":
            trades[-1]['exit'] = price
            trades[-1]['profit'] = price - entry_price
            cumulative_profit += trades[-1]['profit']
            print(f"CLOSE BUY at {price:.2f} | Profit: {trades[-1]['profit']:.2f}")
            position = None
            entry_price = 0
            tp_flags = [False, False, False]

    # Summary
    print(f"\n{symbol} Summary:")
    print(f"Total trades: {len(trades)}")
    print(f"TP1 hits: {tp_hits[0]}, TP2 hits: {tp_hits[1]}, TP3 hits: {tp_hits[2]}")
    print(f"Full TP (TP3) win rate: {tp_hits[2]/len(trades)*100 if trades else 0:.2f}%")
    print(f"Cumulative Profit: {cumulative_profit:.2f}")

    return {
        'total_trades': len(trades),
        'tp_hits': tp_hits,
        'full_tp_win_rate': tp_hits[2]/len(trades)*100 if trades else 0,
        'cumulative_profit': cumulative_profit
    }

# ---------------- RUN BACKTEST FOR ALL INSTRUMENTS ----------------
if __name__ == "__main__":
    results = {}
    for symbol in instruments:
        results[symbol] = backtest_instrument(symbol)

    results_df = pd.DataFrame(results).T
    print("\n--- Consolidated Backtest Results ---")
    print(results_df)
