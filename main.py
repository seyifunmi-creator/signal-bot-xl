# main.py
import MetaTrader5 as mt5
import pandas as pd
import time
from signals_ml import generate_signal
from trade import execute_trade      # your existing trade logic
from dashboard import update_dashboard  # your existing dashboard logic

# -----------------------------
# Trading pairs
# -----------------------------
pairs = ['EURUSD','GBPUSD','USDJPY','USDCAD','XAUUSD']

# -----------------------------
# Initialize MT5
# -----------------------------
if not mt5.initialize():
    print("[ERROR] MT5 initialization failed")
    mt5.shutdown()
    exit()
print("[INFO] Connected to MT5 successfully")

# -----------------------------
# Fetch live data from MT5
# -----------------------------
def get_live_data(pair, n=50, timeframe=mt5.TIMEFRAME_M1):
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
# Main loop: live ML signals
# -----------------------------
try:
    while True:
        print("\n[INFO] Fetching live ML signals...")
        for pair in pairs:
            # Fetch live MT5 data
            pair_data = get_live_data(pair)

            # Generate ML signal
            signal = generate_signal(pair, pair_data)

            # Feed signal into your existing trade logic
            execute_trade(pair, signal)

            # Update dashboard with latest signal
            update_dashboard(pair, signal)

            # Optional: print for monitoring
            print(f"{pair} → Signal={signal}")

        # Adjust interval as needed (e.g., 60 seconds)
        time.sleep(60)

except KeyboardInterrupt:
    print("[INFO] Stopped by user")

finally:
    mt5.shutdown()
