# main.py
import MetaTrader5 as mt5
import pandas as pd
import time
from signals_ml import generate_signal, log_signal
from trade import execute_trade
from dashboard import update_dashboard

# -----------------------------
# Trading pairs and timeframes
# -----------------------------
pairs = ['EURUSD','GBPUSD','USDJPY','USDCAD','XAUUSD']

# Dynamic timeframes dictionary
timeframes = {
    'M1': mt5.TIMEFRAME_M1,
    'M5': mt5.TIMEFRAME_M5,
    'M15': mt5.TIMEFRAME_M15,
    'H1': mt5.TIMEFRAME_H1
}

# Number of candles per timeframe
candles_per_tf_dict = {
    'M1': 50,
    'M5': 30,
    'M15': 20,
    'H1': 15
}

# -----------------------------
# Initialize MT5
# -----------------------------
if not mt5.initialize():
    print("[ERROR] MT5 initialization failed")
    mt5.shutdown()
    exit()
print("[INFO] Connected to MT5 successfully")

# -----------------------------
# Fetch live data
# -----------------------------
def get_live_data(pair, timeframe, n=50):
    """
    Fetch last n candlesticks for a pair
    Returns pandas DataFrame with Open/High/Low/Close
    """
    rates = mt5.copy_rates_from_pos(pair, timeframe, 0, n)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df[['time','open','high','low','close']].rename(
        columns={'open':'Open','high':'High','low':'Low','close':'Close'}
    )

# -----------------------------
# Main loop
# -----------------------------
try:
    while True:
        print("\n[INFO] Fetching live ML signals...")
        for pair in pairs:
            # Fetch multiple timeframe data with variable candle counts
            pair_data_dict = {
                tf: get_live_data(pair, tf_id, candles_per_tf_dict.get(tf, 50))
                for tf, tf_id in timeframes.items()
            }

            # Generate signal
            signal = generate_signal(pair, pair_data_dict, candles_per_tf_dict)

            # Execute trade and update dashboard
            execute_trade(pair, signal)
            update_dashboard(pair, signal)

            # Log signal to CSV
            log_signal(pair, signal)

            # Print for monitoring
            print(f"{pair} → Signal={signal}")

        # Adjust interval as needed (e.g., every 60 seconds)
        time.sleep(60)

except KeyboardInterrupt:
    print("[INFO] Stopped by user")
finally:
    mt5.shutdown()
