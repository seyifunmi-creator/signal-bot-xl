# signals_ml.py
import pandas as pd
import pickle
from datetime import datetime
import sys
import os

# -----------------------------
# Determine correct path for .exe or .py
# -----------------------------
if getattr(sys, 'frozen', False):
    # Running as .exe
    base_path = sys._MEIPASS
else:
    # Running as .py
    base_path = os.path.dirname(__file__)

# Paths
model_path = os.path.join(base_path, "ml_model.pkl")
log_path = os.path.join(base_path, "ml_signals_log.csv")

# -----------------------------
# Load trained ML model
# -----------------------------
with open(model_path, "rb") as f:
    model = pickle.load(f)

# -----------------------------
# Prepare features for ML
# -----------------------------
def prepare_features(pair_data_dict, candles_per_tf_dict=None):
    """
    Combine multiple timeframe data for ML input.
    pair_data_dict: {'M1': df1, 'M5': df5, 'M15': df15, 'H1': dfH1, ...}
    candles_per_tf_dict: number of recent candles per timeframe
    Returns a single-row DataFrame ready for model.predict()
    """
    features = pd.DataFrame()
    for tf, df in pair_data_dict.items():
        if df is not None and not df.empty:
            n_candles = candles_per_tf_dict.get(tf, 50) if candles_per_tf_dict else 50
            last_close = df['Close'].tail(n_candles).reset_index(drop=True)
            last_close.index = [f'{tf}_Close_{i}' for i in range(len(last_close))]
            features = pd.concat([features, last_close], axis=0)
    return features.to_frame().T  # single-row DataFrame

# -----------------------------
# Generate ML signal
# -----------------------------
def generate_signal(pair, pair_data_dict, candles_per_tf_dict=None):
    """
    Returns 'BUY', 'SELL', or None
    """
    try:
        X = prepare_features(pair_data_dict, candles_per_tf_dict)
        if X.empty:
            return None
        prediction = model.predict(X)
        if prediction[0] == 1:
            return "BUY"
        elif prediction[0] == -1:
            return "SELL"
        else:
            return None
    except Exception as e:
        print(f"[ERROR] Failed to generate signal for {pair}: {e}")
        return None

# -----------------------------
# Log signals for backtesting
# -----------------------------
def log_signal(pair, signal):
    """
    Append signal to CSV for analysis
    """
    with open(log_path, "a", newline="") as f:
        f.write(f"{datetime.now()},{pair},{signal}\n")
