# main.py
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import os
import sys
import subprocess
import shutil
import time

# ---------------- CONFIG ----------------
VERSION = "1.1.2"
REPO_OWNER = "yourusername"
REPO_NAME = "precision-bot"
INSTRUMENTS = ["GC=F", "EURUSD=X", "GBPUSD=X", "JPY=X", "CAD=X"]
RSI_PERIOD = 14
PERIOD = "1y"
INTERVAL = "1h"

instrument_params = {
    "GC=F": {"SMA_SHORT":9, "SMA_LONG":28, "TP1":0.004, "TP2":0.008, "TP3":0.012},
    "EURUSD=X": {"SMA_SHORT":10, "SMA_LONG":30, "TP1":0.005, "TP2":0.01, "TP3":0.015},
    "GBPUSD=X": {"SMA_SHORT":9, "SMA_LONG":28, "TP1":0.0045, "TP2":0.009, "TP3":0.0135},
    "JPY=X": {"SMA_SHORT":10, "SMA_LONG":32, "TP1":0.0035, "TP2":0.007, "TP3":0.01},
    "CAD=X": {"SMA_SHORT":9, "SMA_LONG":30, "TP1":0.004, "TP2":0.008, "TP3":0.012}
}

# ---------------- RSI CALC ----------------
def calculate_rsi(df, period=14):
    delta = df['Close'].diff()
    gain = delta.where(delta>0,0)
    loss = -delta.where(delta<0,0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# ---------------- BACKTEST & TRADING ----------------
def run_bot(symbol):
    try:
        df = yf.download(symbol, period=PERIOD, interval=INTERVAL, auto_adjust=True, timeout=60)
    except Exception as e:
        print(f"Download failed for {symbol}: {e}")
        return None

    if df.empty:
        print(f"No data for {symbol}, skipping...")
        return None

    required_cols = ['Close']
    for col in required_cols:
        if col not in df.columns:
            print(f"{col} missing in {symbol}, skipping...")
            return None

    params = instrument_params[symbol]
    SMA_SHORT = params["SMA_SHORT"]
    SMA_LONG = params["SMA_LONG"]
    TP1 = params["TP1"]
    TP2 = params["TP2"]
    TP3 = params["TP3"]

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
        latest = df.iloc[i]  # single row as Series

        price = latest['Close'] if pd.notna(latest['Close']) else np.nan
        sma_short = latest['SMA_SHORT'] if pd.notna(latest['SMA_SHORT']) else np.nan
        sma_long = latest['SMA_LONG'] if pd.notna(latest['SMA_LONG']) else np.nan
        rsi = latest['RSI'] if pd.notna(latest['RSI']) else np.nan

        # Skip rows with missing data
        if np.isnan(price) or np.isnan(sma_short) or np.isnan(sma_long) or np.isnan(rsi):
            continue

        # Signal logic
        if sma_short > sma_long and rsi < 70:
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

        # Open SELL
        elif signal == "SELL" and position != "SELL":
            position = "SELL"
            entry_price = price
            trades.append({'type':'SELL','entry':entry_price,'exit':None,'profit':0})
            tp_flags = [False, False, False]
            print(f"OPEN SELL at {entry_price:.2f}")

        # Check TPs for BUY
        if position == "BUY":
            tp_levels = [entry_price*(1+TP1), entry_price*(1+TP2), entry_price*(1+TP3)]
            for j in range(3):
                if price >= tp_levels[j] and not tp_flags[j]:
                    tp_hits[j] += 1
                    tp_flags[j] = True
                    print(f"HIT TP{j+1} at {price:.2f}")

        # Check TPs for SELL
        if position == "SELL":
            tp_levels = [entry_price*(1-TP1), entry_price*(1-TP2), entry_price*(1-TP3)]
            for j in range(3):
                if price <= tp_levels[j] and not tp_flags[j]:
                    tp_hits[j] += 1
                    tp_flags[j] = True
                    print(f"HIT TP{j+1} at {price:.2f}")

        # Close positions if opposite signal
        if position == "BUY" and signal == "SELL":
            trades[-1]['exit'] = price
            trades[-1]['profit'] = price - entry_price
            cumulative_profit += trades[-1]['profit']
            print(f"CLOSE BUY at {price:.2f} | Profit: {trades[-1]['profit']:.2f}")
            position = None
            entry_price = 0
            tp_flags = [False, False, False]

        elif position == "SELL" and signal == "BUY":
            trades[-1]['exit'] = price
            trades[-1]['profit'] = entry_price - price
            cumulative_profit += trades[-1]['profit']
            print(f"CLOSE SELL at {price:.2f} | Profit: {trades[-1]['profit']:.2f}")
            position = None
            entry_price = 0
            tp_flags = [False, False, False]

    # Accuracy
    accuracy = tp_hits[2]/len(trades)*100 if trades else 0
    print(f"\n{symbol} Summary: Total trades {len(trades)}, TP3 hits {tp_hits[2]}, Accuracy {accuracy:.2f}%")

    # Log trades
    log_trades(symbol, trades, accuracy, cumulative_profit)

    # Auto-update if accuracy < 75%
    if accuracy < 75:
        print("Accuracy below 75% → Checking for updates...")
        auto_update_and_restart()

    return accuracy

# ---------------- LOGGING ----------------
def log_trades(symbol, trades, accuracy, cumulative_profit):
    log_file = f"{symbol.replace('=','')}_log.csv"
    df_log = pd.DataFrame(trades)
    df_log['accuracy'] = accuracy
    df_log['cumulative_profit'] = cumulative_profit
    df_log.to_csv(log_file, index=False)
    print(f"Logged trades to {log_file}")

# ---------------- AUTO-UPDATE + RESTART ----------------
def auto_update_and_restart():
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
        response = requests.get(url).json()
        latest_version = response['tag_name']
        if latest_version != VERSION and response.get('assets'):
            asset_url = response['assets'][0]['browser_download_url']
            print(f"Downloading new version {latest_version}...")
            r = requests.get(asset_url)
            new_file = "main_new.exe"
            with open(new_file, "wb") as f:
                f.write(r.content)
            print("Downloaded new main.exe")

            # Replace old exe and restart
            current_exe = sys.executable
            backup = current_exe + ".bak"
            shutil.move(current_exe, backup)
            shutil.move(new_file, current_exe)
            print("Updated and restarting bot...")
            subprocess.Popen([current_exe])
            sys.exit()
    except Exception as e:
        print(f"Auto-update failed: {e}")

# ---------------- MAIN LOOP ----------------
if __name__== "__main__":
    for symbol in INSTRUMENTS:
        run_bot(symbol)
