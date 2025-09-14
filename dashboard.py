# signals.py

import MetaTrader5 as mt5
import pandas as pd
import config

# --- Strategy Settings ---
EMA_FAST = 3
EMA_SLOW = 6
RSI_PERIOD = 14

def get_data(pair, n=1000, timeframe=mt5.TIMEFRAME_M5):
    """
    Fetch historical data from MT5
    """
    rates = mt5.copy_rates_from_pos(pair, timeframe, 0, n)
    if rates is None:
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

    # Calculate EMAs
    df['ema_fast'] = df['close'].ewm(span=EMA_FAST).mean()
    df['ema_slow'] = df['close'].ewm(span=EMA_SLOW).mean()

    # Calculate RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(RSI_PERIOD).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(RSI_PERIOD).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # Latest values
    ema_fast = df['ema_fast'].iloc[-1]
    ema_slow = df['ema_slow'].iloc[-1]
    rsi = df['rsi'].iloc[-1]

    # Signal rules
    if ema_fast > ema_slow and rsi > 50:
        return "BUY"
    elif ema_fast < ema_slow and rsi < 50:
        return "SELL"
    else:
        return None
