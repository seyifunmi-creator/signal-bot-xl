# signals.py

import MetaTrader5 as mt5
import pandas as pd
import config

EMA_FAST = config.EMA_FAST
EMA_SLOW = config.EMA_SLOW
RSI_PERIOD = 14

# --- Session filter ---
def in_session():
    if not config.USE_SESSION_FILTER:
        return True
    from datetime import datetime
    now = datetime.now().time()
    start = datetime.strptime(config.SESSION_START, "%H:%M").time()
    end = datetime.strptime(config.SESSION_END, "%H:%M").time()
    return start <= now <= end

# --- Data fetching with forced preload ---
def get_data(pair, n=2000, timeframe=mt5.TIMEFRAME_M5):
    """Fetch historical data; force MT5 to load bars if empty"""
    # Ensure symbol is selected
    if not mt5.symbol_select(pair, True):
        print(f"[WARN] Symbol {pair} not available")
        return None

    # Try fetching M5 bars
    rates = mt5.copy_rates_from_pos(pair, timeframe, 0, n)

    # If M5 empty, force MT5 to preload using M1
    if rates is None or len(rates) == 0:
        print(f"[INFO] M5 empty for {pair}, preloading using M1...")
        rates = mt5.copy_rates_from_pos(pair, mt5.TIMEFRAME_M1, 0, n)
        if rates is None or len(rates) == 0:
            print(f"[WARN] No data available for {pair} even after preload")
            return None

        # Resample M1 → M5 to maintain original timeframe
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        df = df['close'].resample('5T').ohlc()
        df.columns = ['open', 'high', 'low', 'close']
        return df

    # If M5 has data, just return it
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

# --- RSI calculation ---
def calculate_rsi(df, period=RSI_PERIOD):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# --- Signal generation ---
def generate_signal(pair, return_values=False):
    """Generate BUY / SELL / None signal"""
    if not in_session():
        if return_values:
            return None, 0, 0, 0
        return None

    df = get_data(pair)
    if df is None or len(df) < max(EMA_SLOW, RSI_PERIOD):
        if return_values:
            return None, 0, 0, 0
        return None

    df['ema_fast'] = df['close'].ewm(span=EMA_FAST, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=EMA_SLOW, adjust=False).mean()
    df['rsi'] = calculate_rsi(df)

    ema_fast = df['ema_fast'].iloc[-1]
    ema_slow = df['ema_slow'].iloc[-1]
    rsi = df['rsi'].iloc[-1]

    signal = None
    if ema_fast > ema_slow and rsi > 50:
        signal = "BUY"
    elif ema_fast < ema_slow and rsi < 50:
        signal = "SELL"

    if return_values:
        return signal, ema_fast, ema_slow, rsi
    return signal
