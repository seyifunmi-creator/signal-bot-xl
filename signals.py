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
CONFIRM_CANDLES = 2  # EMA must hold crossover for 2 consecutive candles

# --- Signal Logging ---
SIGNAL_LOG_FILE = "signal_log.csv"
if not os.path.exists(SIGNAL_LOG_FILE):
    with open(SIGNAL_LOG_FILE, "w") as f:
        f.write("timestamp,pair,signal,ema_fast,ema_slow,rsi,trend_h1\n")

def log_signal(pair, signal, ema_fast, ema_slow, rsi, trend_h1):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(SIGNAL_LOG_FILE, "a") as f:
        f.write(f"{timestamp},{pair},{signal},{ema_fast:.5f},{ema_slow:.5f},{rsi:.2f},{trend_h1}\n")

def get_data(pair, n=1000, timeframe=mt5.TIMEFRAME_M5):
    rates = mt5.copy_rates_from_pos(pair, timeframe, 0, n)
    if rates is None:
        print(f"[WARN] No data for {pair}, market may be closed.")
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

def calculate_trend(df):
    df['ema_fast'] = df['close'].ewm(span=EMA_FAST).mean()
    df['ema_slow'] = df['close'].ewm(span=EMA_SLOW).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(RSI_PERIOD).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(RSI_PERIOD).mean().replace(0, 1e-9)
    df['rsi'] = 100 - (100 / (1 + gain / loss))
    return df

def check_h1_trend(pair):
    df_h1 = get_data(pair, n=100, timeframe=mt5.TIMEFRAME_H1)
    if df_h1 is None or len(df_h1) < RSI_PERIOD:
        return None
    df_h1 = calculate_trend(df_h1)
    return "BUY" if df_h1['ema_fast'].iloc[-1] > df_h1['ema_slow'].iloc[-1] else "SELL"

def generate_signal(pair):
    df = get_data(pair)
    if df is None or len(df) < RSI_PERIOD + CONFIRM_CANDLES:
        return None

    df = calculate_trend(df)
    ema_fast_last = df['ema_fast'].iloc[-CONFIRM_CANDLES:]
    ema_slow_last = df['ema_slow'].iloc[-CONFIRM_CANDLES:]
    rsi = df['rsi'].iloc[-1]

    # Multi-candle confirmation
    if all(ema_fast_last > ema_slow_last) and rsi > 55:
        signal = "BUY"
    elif all(ema_fast_last < ema_slow_last) and rsi < 45:
        signal = "SELL"
    else:
        signal = None

    # H1 trend filter
    trend_h1 = check_h1_trend(pair)
    if signal and trend_h1 and signal != trend_h1:
        signal = None  # Skip counter-trend signals

    # Log signal
    log_signal(pair, signal, df['ema_fast'].iloc[-1], df['ema_slow'].iloc[-1], rsi, trend_h1)
    return signal
