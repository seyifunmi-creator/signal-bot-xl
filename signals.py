# signals.py

import MetaTrader5 as mt5
import pandas as pd
import config
from datetime import datetime

# --- Strategy Settings ---
EMA_FAST = config.EMA_FAST
EMA_SLOW = config.EMA_SLOW
RSI_PERIOD = 14  # default, can be adjusted


# Optional accuracy boost: only trade during session hours
def in_session():
    if not config.USE_SESSION_FILTER:
        return True
    now = datetime.now().time()
    start = datetime.strptime(config.SESSION_START, "%H:%M").time()
    end = datetime.strptime(config.SESSION_END, "%H:%M").time()
    return start <= now <= end


def get_data(pair, n=2000, timeframe=mt5.TIMEFRAME_M5):
    """Fetch historical data from MT5; fallback to M1 if M5 empty"""
    if not mt5.symbol_select(pair, True):
        print(f"[WARN] Symbol {pair} not available")
        return None

    rates = mt5.copy_rates_from_pos(pair, timeframe, 0, n)
    if rates is None or len(rates) == 0:
        # fallback to M1
        rates = mt5.copy_rates_from_pos(pair, mt5.TIMEFRAME_M1, 0, n)
        if rates is None or len(rates) == 0:
            print(f"[WARN] No data for {pair}")
            return None

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df


def calculate_rsi(df, period=RSI_PERIOD):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def generate_signal(pair, return_values=False):
    """Generate BUY / SELL / None signal with EMA + RSI filter"""
    if not in_session():
        if return_values:
            return None, 0, 0, 0
        return None

    df = get_data(pair)
    if df is None or len(df) < max(EMA_SLOW, RSI_PERIOD):
        if return_values:
            return None, 0, 0, 0
        return None

    # --- EMA calculations ---
    df['ema_fast'] = df['close'].ewm(span=EMA_FAST, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=EMA_SLOW, adjust=False).mean()

    # --- RSI calculation ---
    df['rsi'] = calculate_rsi(df)

    # --- Latest values ---
    ema_fast = float(df['ema_fast'].iloc[-1])
    ema_slow = float(df['ema_slow'].iloc[-1])
    rsi = float(df['rsi'].iloc[-1])

    # --- Signal rules ---
    signal = None
    if ema_fast > ema_slow and rsi > 50:
        signal = "BUY"
    elif ema_fast < ema_slow and rsi < 50:
        signal = "SELL"

    # --- Alert when signal is valid ---
    if signal:
        print(f"[ALERT] 🚨 {pair}: {signal} signal | EMA_FAST={ema_fast:.5f}, EMA_SLOW={ema_slow:.5f}, RSI={rsi:.2f}")

    if return_values:
        return signal, ema_fast, ema_slow, rsi
    return signal
