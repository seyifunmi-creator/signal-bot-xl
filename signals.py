import MetaTrader5 as mt5
import pandas as pd

# --- Signal Generation Settings ---
EMA_FAST = 5
EMA_SLOW = 12

# --- Helper Functions ---
def get_historical_data(pair, n=100, timeframe=mt5.TIMEFRAME_H1):
    """
    Fetch last n candles from MT5.
    Returns a DataFrame with columns: time, open, high, low, close, tick_volume.
    """
    rates = mt5.copy_rates_from_pos(pair, timeframe, 0, n)
    if rates is None:
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def calculate_ema(df, period):
    return df['close'].ewm(span=period, adjust=False).mean()

def generate_signal(pair):
    """
    Simple EMA crossover signal:
    - BUY if EMA_FAST crosses above EMA_SLOW
    - SELL if EMA_FAST crosses below EMA_SLOW
    """
    df = get_historical_data(pair)
    if df.empty or len(df) < EMA_SLOW:
        return None

    df['EMA_FAST'] = calculate_ema(df, EMA_FAST)
    df['EMA_SLOW'] = calculate_ema(df, EMA_SLOW)

    if df['EMA_FAST'].iloc[-2] < df['EMA_SLOW'].iloc[-2] and df['EMA_FAST'].iloc[-1] > df['EMA_SLOW'].iloc[-1]:
        return "BUY"
    elif df['EMA_FAST'].iloc[-2] > df['EMA_SLOW'].iloc[-2] and df['EMA_FAST'].iloc[-1] < df['EMA_SLOW'].iloc[-1]:
        return "SELL"
    else:
        return None
