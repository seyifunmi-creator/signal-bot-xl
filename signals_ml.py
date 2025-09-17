# signals_ml.py
import os
import sys
import pickle
import pandas as pd
from datetime import datetime

# -----------------------------
# Determine base path for .exe or .py
# -----------------------------
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(__file__)

# Paths
model_path = os.path.join(base_path, "ml_model.pkl")
log_path = os.path.join(base_path, "ml_signals_log.csv")

# -----------------------------
# Load trained ML model
# -----------------------------
try:
    with open(model_path, "rb") as f:
        model = pickle.load(f)
except Exception as e:
    print(f"❌ Failed to load ML model: {e}")
    model = None

# -----------------------------
# Generate signal for a pair
# -----------------------------
def generate_signal(pair, pair_data_dict=None, candles_per_tf_dict=None):
    if model is None:
        return None

    try:
        # Use last candle features if data exists
        X = [[0, 0, 0, 0]]  # Default dummy features
        if pair_data_dict:
            df = pair_data_dict.get('M1')
            if df is not None and not df.empty:
                last_candle = df.iloc[-1]
                X = [[
                    last_candle['Open'],
                    last_candle['High'],
                    last_candle['Low'],
                    last_candle['Close']
                ]]
        signal_num = model.predict(X)[0]
        return "BUY" if signal_num == 1 else "SELL"
    except Exception as e:
        print(f"❌ Error generating signal: {e}")
        return None

# -----------------------------
# Log multiple signals to CSV
# -----------------------------
def log_ml_signals(pairs):
    if model is None:
        return

    log_entries = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for pair in pairs:
        signal = generate_signal(pair)
        log_entries.append({"Time": now, "Pair": pair, "Signal": signal})

    df_log = pd.DataFrame(log_entries)
    if os.path.exists(log_path):
        df_log.to_csv(log_path, mode='a', index=False, header=False)
    else:
        df_log.to_csv(log_path, index=False)
    return log_entries

# -----------------------------
# Log a single signal
# -----------------------------
def log_signal(pair, signal):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df_entry = pd.DataFrame([{"Time": now, "Pair": pair, "Signal": signal}])
    if os.path.exists(log_path):
        df_entry.to_csv(log_path, mode='a', index=False, header=False)
    else:
        df_entry.to_csv(log_path, index=False)
