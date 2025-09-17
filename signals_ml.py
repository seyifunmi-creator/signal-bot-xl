# signals_ml.py
import pandas as pd
import pickle
import sys
import os
from datetime import datetime

# -----------------------------
# Determine correct path for .exe or .py
# -----------------------------
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS  # PyInstaller .exe
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
    print("✅ ML model loaded successfully!")
except Exception as e:
    print(f"❌ Failed to load ML model: {e}")
    model = None

# -----------------------------
# Generate signal for a pair
# -----------------------------
def generate_signal(pair, pair_data_dict, candles_per_tf_dict):
    """
    pair: str, trading pair
    pair_data_dict: dict of DataFrames per timeframe
    candles_per_tf_dict: dict, number of candles per timeframe

    Returns: "BUY", "SELL", or None
    """
    if model is None:
        return None

    # Example: take latest candle from M1
    df_m1 = pair_data_dict.get('M1')
    if df_m1 is None or df_m1.empty:
        return None

    latest_candle = df_m1.iloc[-1]
    features = [latest_candle['Open'], latest_candle['High'], latest_candle['Low'], latest_candle['Close']]

    try:
        pred = model.predict([features])[0]
        return "BUY" if pred == 1 else "SELL"
    except Exception as e:
        print(f"❌ Error generating signal for {pair}: {e}")
        return None

# -----------------------------
# Log signal to CSV
# -----------------------------
def log_signal(pair, signal):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = {"datetime": now, "pair": pair, "signal": signal}

    try:
        if not os.path.exists(log_path):
            df = pd.DataFrame([row])
            df.to_csv(log_path, index=False)
        else:
            df = pd.read_csv(log_path)
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            df.to_csv(log_path, index=False)
        # Optional print for monitoring
        # print(f"[INFO] Logged signal: {pair} → {signal}")
    except Exception as e:
        print(f"❌ Failed to log signal: {e}")
