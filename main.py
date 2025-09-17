# main.py
import MetaTrader5 as mt5
import pandas as pd
import time
import sys
import os
from signals_ml import generate_signal, log_ml_signals
from trade import execute_trade
from dashboard import update_dashboard

# -----------------------------
# Determine base path for .exe or .py
# -----------------------------
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS  # for PyInstaller .exe
else:
    base_path = os.path.dirname(__file__)

# -----------------------------
# Trading pairs and timeframes
# -----------------------------
pairs = ['EURUSD','GBPUSD','USDJPY','USDCAD','XAUUSD']

# MetaTrader5 timeframes
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
        ml_signals_logs = []  # store signals for logging

        for pair in pairs:
            # Fetch data for each timeframe
            pair_data_dict = {
                tf: get_live_data(pair, tf_id, candles_per_tf_dict.get(tf, 50))
                for tf, tf_id in timeframes.items()
            }

            # For ML, we only need the most recent timeframe data (e.g., M1)
            df_latest = pair_data_dict['M1']
            signal = generate_signal(df_latest)

            # Execute trade and update dashboard
            execute_trade(pair, signal)
            update_dashboard(pair, signal)

            # Store for ML logging
            ml_signals_logs.append({'Pair': pair, 'Signal': signal})

            # Print for monitoring
            print(f"{pair} → Signal={signal}")

        # Log all ML signals at once
        log_ml_signals(pairs)

        # Wait 60 seconds before next iteration
        time.sleep(60)

except KeyboardInterrupt:
    print("[INFO] Stopped by user")
finally:
    mt5.shutdown()
