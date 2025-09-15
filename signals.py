# signals.py

import MetaTrader5 as mt5
import pandas as pd
import config
from datetime import datetime
import os

# --- Strategy Settings ---
EMA_FAST = 3
EMA_SLOW = 6
RSI_PERIOD = 14

# --- Signal Logging Setup ---
SIGNAL_LOG_FILE = "signal_log.csv"
if not os.path.exists(SIGNAL_LOG_FILE):
    with open(SIGNAL_LOG_FILE, "w") as f:
        f.write("timestamp,pair,signal,ema_fast,ema_slow,rsi\n")

def log_signal(pair, signal, ema_fast, ema_slow, rsi):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(SIGNAL_LOG_FILE, "a") as f:
        f.write(f"{timestamp},{pair},{signal},{ema_fast:.5f},{ema_slow:.5f},{rsi:.2f}\n")

def get_data(pair, n=1000, timeframe=mt5.TIMEFRAME_M5):
    """
    Fetch historical data from MT5
    """
    rates = mt5.copy_rates_from_pos(pair, timeframe, 0, n)
    if rates is None:
        print(f"[WARN] No data for {pair}, market may be closed.")
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

def generate_signal(pair):
    """
    Generate BUY / SELL / None signal using EMA crossover + RSI filter
    """
    df = get_data(pair)
    if df is None or len(df) < RSI_PERIOD:
        return None

    # --- Calculate EMAs ---
    df['ema_fast'] = df['close'].ewm(span=EMA_FAST).mean()
    df['ema_slow'] = df['close'].ewm(span=EMA_SLOW).mean()

    # --- Calculate RSI ---
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(RSI_PERIOD).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(RSI_PERIOD).mean()
    # Prevent division by zero
    loss = loss.replace(0, 1e-9)
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # --- Latest values ---
    ema_fast = df['ema_fast'].iloc[-1]
    ema_slow = df['ema_slow'].iloc[-1]
    rsi = df['rsi'].iloc[-1]

    # --- Signal rules ---
    if ema_fast > ema_slow and rsi > 50:
        signal = "BUY"
    elif ema_fast < ema_slow and rsi < 50:
        signal = "SELL"
    else:
        signal = None

    # --- Log every signal ---
    log_signal(pair, signal, ema_fast, ema_slow, rsi)

    return signal
